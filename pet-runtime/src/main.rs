//! Desktop Pet Runtime — entry point.
//!
//! Loads compile-time-embedded sprite sheets, sets up the Bevy app with a
//! transparent always-on-top window, and assembles the runtime from small
//! single-responsibility plugins.
//!
//! ## Module map
//!
//! | Module | Responsibility |
//! |--------|----------------|
//! | [`config`] | every tunable constant (geometry, thresholds, durations) |
//! | [`window`] | transparent overlay window + physical-pixel position anchor |
//! | [`animation`] | `AnimState` taxonomy, sheet playback, state machine |
//! | [`pet`] | vitals & mood |
//! | [`behavior`] | autonomous actions |
//! | [`interaction`] | pointer → drag / stroke / menu, squash feedback |
//! | [`command`] | user-intent message bus + the single effect handler |
//! | [`achievements`] | achievement bookkeeping |
//! | [`ui`] | menu, HUD, toasts (ASCII-only text, node-drawn icons) |
//! | [`tray`] | optional system tray (`--features tray`) |
//!
//! Input surfaces never mutate the pet directly: they emit
//! [`command::PetCommand`] messages, which keeps every surface (sprite, menu,
//! tray, future hotkeys) decoupled from the rules.
//!
//! ## Sprite-sheet embedding
//!
//! The generator pipeline inserts entries into `SPRITE_SHEETS` at build time.
//! Each entry is a 5-tuple `(AnimState, png_bytes, fps, loop_anim, duration_secs)`.
//! At startup every sheet is decoded, uploaded to the GPU, and registered in
//! `AnimationAssets`.

mod achievements;
mod animation;
mod behavior;
mod command;
mod config;
mod interaction;
mod pet;
mod tray;
mod ui;
mod window;

use std::collections::hash_map::Entry;
use std::collections::{HashMap, HashSet};

use bevy::asset::RenderAssetUsages;
use bevy::prelude::*;
use bevy::render::render_resource::{Extent3d, TextureDimension, TextureFormat};
use image::GenericImageView as _;

use animation::{AnimState, AnimationAssets, FramePlayer, SpriteAnimation};
use config::SPRITE_SIZE;
use pet::Pet;

// ---------------------------------------------------------------------------
// Compile-time embedded assets
// ---------------------------------------------------------------------------

/// Sprite sheets embedded at compile time.
/// Format: `(AnimState, png_bytes, fps, loop_anim, duration_secs)`.
///
/// The generator pipeline will insert entries here, e.g.:
/// ```ignore
/// const SPRITE_SHEETS: &[(AnimState, &[u8], f32, bool, f32)] = &[
///     (AnimState::Idle,  include_bytes!("../assets/idle.png"),  8.0, true,  3.0),
///     (AnimState::Happy, include_bytes!("../assets/happy.png"), 10.0, false, 1.5),
/// ];
/// ```
// GENERATOR-CONTRACT: DO NOT EDIT — kept in sync by pet_generator/runtime_gen/rust_project.py
const SPRITE_SHEETS: &[(AnimState, &[u8], f32, bool, f32)] = &[
    // Generator will insert entries here
];

/// Fallback sprite shown when no animation data is available at all.
const FALLBACK_SPRITE: &[u8] = include_bytes!("../assets/fallback.png");

/// Pixel size of each square frame in the sprite sheets.
// GENERATOR-CONTRACT: DO NOT EDIT — patched from manifest.frame_size by the generator
const FRAME_SIZE: u32 = 256;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Decode PNG bytes into a Bevy `Image` via the `image` crate.
/// Used for the single-frame fallback sprite.
fn decode_png(bytes: &[u8]) -> Option<Image> {
    match image::load_from_memory(bytes) {
        Ok(dyn_img) => {
            let rgba = dyn_img.to_rgba8();
            let extent = Extent3d {
                width: rgba.width(),
                height: rgba.height(),
                depth_or_array_layers: 1,
            };
            Some(Image::new(
                extent,
                TextureDimension::D2,
                rgba.into_raw(),
                TextureFormat::Rgba8UnormSrgb,
                RenderAssetUsages::default(),
            ))
        }
        Err(e) => {
            warn!("Failed to decode PNG: {e}");
            None
        }
    }
}

/// Split a horizontal sprite sheet into individual frame texture handles on the
/// CPU side.
///
/// Each frame is `frame_size × frame_size`, so every uploaded texture stays well
/// within any GPU/wgpu max-texture-dimension limit (sheets wider than 8192 px
/// would otherwise fail). `RenderAssetUsages::default()` keeps the pixels in the
/// main world too, which the pointer layer uses for alpha hit-testing.
fn decode_sprite_sheet(
    data: &[u8],
    frame_size: u32,
    images: &mut Assets<Image>,
) -> Vec<Handle<Image>> {
    let Ok(decoded) = image::load_from_memory(data) else {
        warn!("Sprite sheet decode failed; skipping");
        return Vec::new();
    };
    let rgba = decoded.to_rgba8();
    let sheet_height = rgba.height().min(frame_size);
    let cols = rgba.width() / frame_size;

    let mut frames = Vec::with_capacity(cols as usize);
    for col in 0..cols {
        let frame = rgba
            .view(col * frame_size, 0, frame_size, sheet_height)
            .to_image();
        let extent = Extent3d {
            width: frame.width(),
            height: frame.height(),
            depth_or_array_layers: 1,
        };
        frames.push(images.add(Image::new(
            extent,
            TextureDimension::D2,
            frame.into_raw(),
            TextureFormat::Rgba8UnormSrgb,
            RenderAssetUsages::default(),
        )));
    }
    frames
}

// ---------------------------------------------------------------------------
// Startup
// ---------------------------------------------------------------------------

/// Decode every embedded sprite sheet (CPU-side per-frame slicing) and register
/// the results in [`AnimationAssets`].
fn load_animations(mut commands: Commands, mut images: ResMut<Assets<Image>>) {
    let mut animations: HashMap<AnimState, SpriteAnimation> = HashMap::new();

    for &(state, png_bytes, fps, loop_anim, duration_secs) in SPRITE_SHEETS {
        let frames = decode_sprite_sheet(png_bytes, FRAME_SIZE, &mut images);
        if frames.is_empty() {
            warn!("Skipping animation {:?}: no frames decoded", state);
            continue;
        }
        // A positive `duration_secs` becomes the sheet's suggested duration;
        // otherwise leave it to callers (looping sheets get a caller-supplied
        // countdown, non-looping sheets play to finish).
        let default_duration = (duration_secs > 0.0).then_some(duration_secs);
        info!(
            "Loaded animation {:?}: {} frames @ {} fps (loop={}, duration={:?})",
            state,
            frames.len(),
            fps,
            loop_anim,
            default_duration
        );
        animations.insert(
            state,
            SpriteAnimation {
                frames,
                fps,
                loop_anim,
                default_duration,
            },
        );
    }

    // If no Idle animation was provided, register the fallback sprite so the pet
    // is at least visible.
    if let Entry::Vacant(slot) = animations.entry(AnimState::Idle) {
        if let Some(fallback_img) = decode_png(FALLBACK_SPRITE) {
            let handle = images.add(fallback_img);
            slot.insert(SpriteAnimation {
                frames: vec![handle],
                fps: 1.0,
                loop_anim: true,
                default_duration: None,
            });
            info!("Registered fallback sprite as Idle");
        } else {
            error!("Fallback sprite decode failed — pet will be invisible!");
        }
    }

    // The set of states that actually decoded successfully. Consumers (mood
    // mapping, autonomous behaviour, menu) intersect with this to stay
    // body-type-agnostic.
    let available: HashSet<AnimState> = animations.keys().copied().collect();

    commands.insert_resource(AnimationAssets {
        animations,
        available,
    });
}

/// Spawn the pet sprite entity using the first frame of the Idle animation.
fn spawn_pet(mut commands: Commands, assets: Res<AnimationAssets>) {
    let Some(idle) = assets.animations.get(&AnimState::Idle) else {
        error!("No Idle animation available — cannot spawn pet");
        return;
    };
    let Some(first_frame) = idle.frames.first() else {
        error!("Idle animation has no frames — cannot spawn pet");
        return;
    };

    commands.spawn((
        Sprite {
            image: first_frame.clone(),
            custom_size: Some(Vec2::splat(SPRITE_SIZE)),
            ..default()
        },
        // Explicit `Transform` for the squash-and-stretch system (`Sprite` also
        // auto-requires one; declaring it makes the dependency obvious).
        Transform::default(),
        FramePlayer::default(),
        Pet::default(),
    ));
}

/// Spawn the 2D camera required for any rendering to occur.
fn setup_camera(mut commands: Commands) {
    commands.spawn(Camera2d);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

fn main() {
    App::new()
        // Transparent clear colour — alpha must be 0, otherwise colour bleeds
        // through the transparent window (official Bevy example recipe).
        .insert_resource(ClearColor(Color::NONE))
        .add_plugins(
            DefaultPlugins
                .set(window::window_plugin())
                // Linear filtering: frames are FRAME_SIZE² but drawn at
                // SPRITE_SIZE logical px (≈1.6× upscale on HiDPI), where nearest
                // sampling shows visible stair-stepping.
                .set(ImagePlugin::default()),
        )
        // -- runtime plugins ------------------------------------------------
        .add_plugins((
            window::PetWindowPlugin,
            animation::AnimationPlugin,
            pet::PetPlugin,
            behavior::BehaviorPlugin,
            command::CommandPlugin,
            interaction::InteractionPlugin,
            achievements::AchievementsPlugin,
            ui::PetUiPlugin,
            // System tray: a full plugin with `--features tray`, else a no-op.
            tray::TrayPlugin,
        ))
        // -- explicit frame pipeline ----------------------------------------
        // Window position is refreshed first, then pointer input is turned into
        // intents, UI rows may add more intents, the command handler applies
        // them, autonomous behaviour fills the silence, playback renders the
        // resulting state and the HUD/toasts present it.
        .configure_sets(
            Update,
            (
                window::WindowAnchorSystems,
                interaction::InteractionSystems,
                ui::PetUiSystems::Input,
                command::CommandSystems,
                behavior::BehaviorSystems,
                animation::AnimationSystems,
                ui::PetUiSystems::Present,
            )
                .chain(),
        )
        // -- startup --------------------------------------------------------
        .add_systems(
            Startup,
            (
                setup_camera,
                load_animations,
                spawn_pet.after(load_animations),
            ),
        )
        .run();
}
