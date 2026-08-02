//! Pointer interaction: window dragging, sprite hit-testing, click-vs-drag
//! discrimination and squash-and-stretch feedback.
//!
//! ## Dragging model
//!
//! The window is moved by writing [`Window::position`] as
//! [`WindowPosition::At`], which is in **physical** pixels. Everything here
//! therefore works in physical pixels and never mixes units:
//!
//! 1. on press we remember the *grab point* — the cursor position inside the
//!    window ([`Window::physical_cursor_position`], physical px);
//! 2. every frame we compute `delta = cursor_now - grab`. Because the window is
//!    moved by exactly `delta`, the cursor lands back on the grab point, so
//!    `delta` naturally becomes the per-frame movement and the loop is
//!    **self-correcting** (a lagging window catches up instead of drifting);
//! 3. the authoritative window position comes from [`WindowAnchor`], which is
//!    seeded by a deliberate initial placement and kept honest by the OS's
//!    [`WindowMoved`](bevy::window::WindowMoved) messages.
//!
//! Mouse *motion* messages are deliberately **not** used: on macOS they are
//! logical points while the window position is physical pixels, and on Windows
//! they are raw device units — both would drift.
//!
//! ## Click vs. drag
//!
//! A press only becomes a drag once the cursor travels past
//! [`DRAG_THRESHOLD`]. A release below the threshold is a *pet* interaction,
//! and only if the press actually landed on a non-transparent sprite pixel
//! (alpha hit test) — clicking the transparent margins does nothing.
//!
//! UI regions ([`UiBlocker`]) always win over the sprite, so menu clicks never
//! pet or drag the pet.

use bevy::prelude::*;
use bevy::window::{PrimaryWindow, WindowPosition};

use crate::animation::{AnimStateMachine, FramePlayer};
use crate::command::{CommandSystems, PetCommand};
use crate::config::{
    ALPHA_HIT_THRESHOLD, DRAG_THRESHOLD, SPRITE_SIZE, SQUASH_MAX, SQUASH_PER_SPEED,
};
use crate::ui::{MenuRoot, MenuState, UiBlocker};
use crate::window::{WindowAnchor, WindowAnchorSystems};

/// System set covering pointer handling.
#[derive(SystemSet, Debug, Clone, PartialEq, Eq, Hash)]
pub struct InteractionSystems;

/// An in-flight left-button press that started on the pet.
#[derive(Debug, Clone, Copy)]
struct Press {
    /// Cursor position inside the window when the press started (physical px).
    grab: Vec2,
    /// Whether the press has already been promoted to a drag.
    dragging: bool,
}

/// Pointer bookkeeping shared between the press tracker and the visual feedback.
#[derive(Resource, Default)]
pub struct PointerState {
    press: Option<Press>,
    /// Instantaneous drag speed in logical px per frame (drives squash).
    speed: f32,
}

impl PointerState {
    /// Whether a real drag (past the threshold) is currently in progress.
    pub fn is_dragging(&self) -> bool {
        self.press.is_some_and(|p| p.dragging)
    }
}

/// Registers pointer handling and drag feedback.
pub struct InteractionPlugin;

impl Plugin for InteractionPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<PointerState>().add_systems(
            Update,
            (pointer_system, apply_drag_squash)
                .chain()
                .in_set(InteractionSystems)
                .after(WindowAnchorSystems)
                .before(CommandSystems),
        );
    }
}

// ---------------------------------------------------------------------------
// Pure geometry helpers (unit-tested)
// ---------------------------------------------------------------------------

/// Map a window-relative cursor position to normalised sprite coordinates.
///
/// * `cursor_logical` — cursor in logical px, origin top-left of the window;
/// * `window_size` / `sprite_size` — logical px.
///
/// Returns `None` when the cursor is outside the sprite's bounding box, else
/// `Some((u, v))` in `0.0..1.0` with `v` growing downwards (texture order).
pub fn sprite_uv(cursor_logical: Vec2, window_size: Vec2, sprite_size: Vec2) -> Option<Vec2> {
    // The 2D camera is centred on the window and the sprite sits at the world
    // origin, so the sprite's top-left corner is at (window - sprite) / 2.
    let origin = (window_size - sprite_size) * 0.5;
    let local = cursor_logical - origin;
    if local.x < 0.0 || local.y < 0.0 || local.x >= sprite_size.x || local.y >= sprite_size.y {
        return None;
    }
    Some(Vec2::new(local.x / sprite_size.x, local.y / sprite_size.y))
}

/// Convert normalised sprite coordinates to integer texel coordinates.
pub fn uv_to_texel(uv: Vec2, texture_size: UVec2) -> UVec2 {
    let x = (uv.x * texture_size.x as f32).floor() as u32;
    let y = (uv.y * texture_size.y as f32).floor() as u32;
    UVec2::new(
        x.min(texture_size.x.saturating_sub(1)),
        y.min(texture_size.y.saturating_sub(1)),
    )
}

/// Squash-and-stretch scale for a drag `speed` in logical px per frame.
pub fn squash_scale(speed: f32) -> Vec3 {
    let s = (speed * SQUASH_PER_SPEED).clamp(0.0, SQUASH_MAX);
    Vec3::new(1.0 - s, 1.0 + s, 1.0)
}

// ---------------------------------------------------------------------------
// Systems
// ---------------------------------------------------------------------------

/// Test whether a UI region contains the (physical) cursor position.
fn ui_contains(
    query: &Query<(&ComputedNode, &UiGlobalTransform, &InheritedVisibility), With<UiBlocker>>,
    cursor_physical: Vec2,
) -> bool {
    query.iter().any(|(node, transform, visibility)| {
        visibility.get() && node.contains_point(*transform, cursor_physical)
    })
}

/// Test whether the menu (when shown) contains the (physical) cursor position.
fn menu_contains(
    query: &Query<(&ComputedNode, &UiGlobalTransform, &InheritedVisibility), With<MenuRoot>>,
    cursor_physical: Vec2,
) -> bool {
    query.iter().any(|(node, transform, visibility)| {
        visibility.get() && node.contains_point(*transform, cursor_physical)
    })
}

/// Whether the cursor is over an opaque pixel of the pet sprite.
fn hit_test_sprite(
    window: &Window,
    sprite: &Sprite,
    images: &Assets<Image>,
    cursor_physical: Vec2,
) -> bool {
    let scale = window.scale_factor().max(0.1);
    let cursor_logical = cursor_physical / scale;
    let window_size = Vec2::new(window.width(), window.height());
    let sprite_size = sprite.custom_size.unwrap_or(Vec2::splat(SPRITE_SIZE));

    let Some(uv) = sprite_uv(cursor_logical, window_size, sprite_size) else {
        return false;
    };
    // Bounding-box hit is the answer whenever the pixels are unavailable
    // (e.g. an image whose CPU-side data was released).
    let Some(image) = images.get(&sprite.image) else {
        return true;
    };
    let texel = uv_to_texel(uv, image.size());
    image
        .get_color_at(texel.x, texel.y)
        .map(|color| color.alpha() > ALPHA_HIT_THRESHOLD)
        .unwrap_or(true)
}

/// Track the left-button press lifecycle: drag the window, emit
/// [`PetCommand::Pet`] on a click, and dismiss the menu on an outside click.
///
/// Right-click toggles the menu at the cursor.
#[allow(clippy::too_many_arguments)]
pub fn pointer_system(
    mouse: Res<ButtonInput<MouseButton>>,
    mut windows: Query<&mut Window, With<PrimaryWindow>>,
    mut anchor: ResMut<WindowAnchor>,
    mut pointer: ResMut<PointerState>,
    mut menu: ResMut<MenuState>,
    mut sm: ResMut<AnimStateMachine>,
    mut commands: MessageWriter<PetCommand>,
    sprites: Query<&Sprite, With<FramePlayer>>,
    images: Res<Assets<Image>>,
    blockers: Query<(&ComputedNode, &UiGlobalTransform, &InheritedVisibility), With<UiBlocker>>,
    menu_root: Query<(&ComputedNode, &UiGlobalTransform, &InheritedVisibility), With<MenuRoot>>,
) {
    let Ok(mut window) = windows.single_mut() else {
        return;
    };
    let cursor = window.physical_cursor_position();

    // -- right click: toggle the menu at the cursor -------------------------
    if mouse.just_pressed(MouseButton::Right) {
        if let Some(position) = window.cursor_position() {
            menu.anchor = position;
        }
        menu.visible = !menu.visible;
    }

    // -- press -------------------------------------------------------------
    if mouse.just_pressed(MouseButton::Left) {
        pointer.press = None;
        pointer.speed = 0.0;

        if let Some(cursor) = cursor {
            let over_menu = menu_contains(&menu_root, cursor);
            let over_ui = ui_contains(&blockers, cursor);

            if menu.visible && !over_menu {
                // Click outside an open menu dismisses it and is consumed.
                menu.visible = false;
            } else if !over_ui {
                let on_pet = sprites
                    .iter()
                    .any(|sprite| hit_test_sprite(&window, sprite, &images, cursor));
                if on_pet {
                    pointer.press = Some(Press {
                        grab: cursor,
                        dragging: false,
                    });
                }
            }
        }
    }

    // -- hold: drag the window ---------------------------------------------
    if let (Some(press), Some(cursor)) = (pointer.press.as_mut(), cursor) {
        if mouse.pressed(MouseButton::Left) {
            let scale = window.scale_factor().max(0.1);
            let delta = cursor - press.grab;

            if !press.dragging && delta.length() > DRAG_THRESHOLD * scale {
                press.dragging = true;
                sm.dragging = true;
            }

            if press.dragging {
                pointer.speed = delta.length() / scale;
                let step = IVec2::new(delta.x.round() as i32, delta.y.round() as i32);
                if step != IVec2::ZERO {
                    if let Some(next) = anchor.offset(step) {
                        window.position = WindowPosition::At(next);
                    }
                }
            }
        }
    }

    // -- release -----------------------------------------------------------
    if mouse.just_released(MouseButton::Left) {
        if let Some(press) = pointer.press.take() {
            // A press only exists when it started on the pet, so a release that
            // never crossed the threshold is unambiguously a stroke.
            if !press.dragging {
                commands.write(PetCommand::Pet);
            }
        }
        // Defensive: never leave the drag pose latched if the press was lost
        // (e.g. focus stolen mid-drag by another application).
        sm.dragging = false;
        pointer.speed = 0.0;
    }
}

/// Squash-and-stretch feedback while dragging.
///
/// A fast drag stretches the pet vertically and squashes it horizontally; the
/// effect returns to identity as soon as the drag ends.
pub fn apply_drag_squash(
    pointer: Res<PointerState>,
    mut query: Query<&mut Transform, With<FramePlayer>>,
) {
    let dragging = pointer.is_dragging();
    for mut transform in &mut query {
        if dragging {
            transform.scale = squash_scale(pointer.speed);
        } else if transform.scale != Vec3::ONE {
            transform.scale = Vec3::ONE;
        }
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    const WINDOW: Vec2 = Vec2::splat(300.0);
    const SPRITE: Vec2 = Vec2::splat(210.0);

    #[test]
    fn sprite_uv_centre_is_half() {
        let uv = sprite_uv(WINDOW * 0.5, WINDOW, SPRITE).expect("centre must hit");
        assert!((uv.x - 0.5).abs() < 1e-6 && (uv.y - 0.5).abs() < 1e-6);
    }

    #[test]
    fn sprite_uv_rejects_outside_bounding_box() {
        // The sprite occupies 45..255 in a 300 px window.
        assert!(sprite_uv(Vec2::new(10.0, 150.0), WINDOW, SPRITE).is_none());
        assert!(sprite_uv(Vec2::new(150.0, 290.0), WINDOW, SPRITE).is_none());
        assert!(sprite_uv(Vec2::new(46.0, 46.0), WINDOW, SPRITE).is_some());
    }

    #[test]
    fn sprite_uv_top_left_corner_is_origin() {
        let origin = (WINDOW - SPRITE) * 0.5;
        let uv = sprite_uv(origin, WINDOW, SPRITE).expect("corner must hit");
        assert_eq!(uv, Vec2::ZERO);
    }

    #[test]
    fn uv_to_texel_clamps_to_last_pixel() {
        assert_eq!(
            uv_to_texel(Vec2::new(0.999_9, 0.999_9), UVec2::splat(256)),
            UVec2::splat(255)
        );
        assert_eq!(uv_to_texel(Vec2::ZERO, UVec2::splat(256)), UVec2::ZERO);
        assert_eq!(
            uv_to_texel(Vec2::splat(1.0), UVec2::splat(256)),
            UVec2::splat(255),
            "out-of-range uv must never index past the texture"
        );
    }

    #[test]
    fn squash_is_volume_preserving_and_bounded() {
        assert_eq!(squash_scale(0.0), Vec3::ONE);

        let fast = squash_scale(10_000.0);
        assert!((fast.x - (1.0 - SQUASH_MAX)).abs() < 1e-6);
        assert!((fast.y - (1.0 + SQUASH_MAX)).abs() < 1e-6);

        let mid = squash_scale(10.0);
        assert!(mid.x < 1.0 && mid.y > 1.0, "stretch along the drag axis");
    }

    #[test]
    fn drag_threshold_scales_with_hidpi() {
        // 3 logical px of travel on a 2× display is 6 physical px, which must
        // still be below the threshold (4 logical px = 8 physical px).
        let scale = 2.0;
        let travel_physical = 3.0 * scale;
        assert!(travel_physical <= DRAG_THRESHOLD * scale);

        let travel_physical = 5.0 * scale;
        assert!(travel_physical > DRAG_THRESHOLD * scale);
    }

    // -----------------------------------------------------------------------
    // Headless behaviour tests
    //
    // These drive `pointer_system` in a minimal `App`, which is what actually
    // regressed in the field: dragging never moved the window, and clicking
    // anywhere in the transparent overlay counted as petting.
    // -----------------------------------------------------------------------

    use bevy::math::DVec2;

    /// Collects emitted commands so assertions can inspect them.
    #[derive(Resource, Default)]
    struct Collected(Vec<PetCommand>);

    fn collect(mut reader: MessageReader<PetCommand>, mut collected: ResMut<Collected>) {
        collected.0.extend(reader.read().copied());
    }

    /// Minimal app: one 300×300 window (scale factor 1) and one pet sprite.
    fn harness() -> App {
        let mut app = App::new();
        app.init_resource::<ButtonInput<MouseButton>>()
            .init_resource::<WindowAnchor>()
            .init_resource::<PointerState>()
            .init_resource::<MenuState>()
            .init_resource::<AnimStateMachine>()
            .init_resource::<Assets<Image>>()
            .init_resource::<Collected>()
            .add_message::<PetCommand>()
            .add_systems(Update, (pointer_system, collect).chain());

        app.world_mut().spawn((
            Window {
                resolution: (300u32, 300u32).into(),
                ..default()
            },
            PrimaryWindow,
        ));
        app.world_mut().spawn((
            Sprite {
                custom_size: Some(Vec2::splat(SPRITE_SIZE)),
                ..default()
            },
            FramePlayer::default(),
        ));
        // A known anchor stands in for the deliberate startup placement.
        app.world_mut().resource_mut::<WindowAnchor>().physical = Some(IVec2::new(100, 200));
        app
    }

    fn set_cursor(app: &mut App, position: Vec2) {
        let mut windows = app
            .world_mut()
            .query_filtered::<&mut Window, With<PrimaryWindow>>();
        let mut window = windows.single_mut(app.world_mut()).expect("window exists");
        window.set_physical_cursor_position(Some(DVec2::new(position.x as f64, position.y as f64)));
    }

    fn window_position(app: &mut App) -> WindowPosition {
        let mut windows = app
            .world_mut()
            .query_filtered::<&Window, With<PrimaryWindow>>();
        windows.single(app.world()).expect("window exists").position
    }

    fn press_left(app: &mut App) {
        app.world_mut()
            .resource_mut::<ButtonInput<MouseButton>>()
            .press(MouseButton::Left);
    }

    fn release_left(app: &mut App) {
        app.world_mut()
            .resource_mut::<ButtonInput<MouseButton>>()
            .release(MouseButton::Left);
    }

    /// Advance one frame, then clear the just-pressed / just-released latches
    /// exactly like `bevy_input` does between frames.
    fn step(app: &mut App) {
        app.update();
        app.world_mut()
            .resource_mut::<ButtonInput<MouseButton>>()
            .clear();
    }

    const CENTRE: Vec2 = Vec2::splat(150.0);

    #[test]
    fn click_on_the_pet_emits_a_pet_command() {
        let mut app = harness();
        set_cursor(&mut app, CENTRE);

        press_left(&mut app);
        step(&mut app);
        release_left(&mut app);
        step(&mut app);

        assert_eq!(app.world().resource::<Collected>().0, vec![PetCommand::Pet]);
        assert!(
            matches!(window_position(&mut app), WindowPosition::Automatic),
            "a click must not move the window"
        );
    }

    #[test]
    fn drag_moves_the_window_by_the_cursor_delta() {
        let mut app = harness();
        set_cursor(&mut app, CENTRE);

        press_left(&mut app);
        step(&mut app);

        // Move well past the threshold.
        set_cursor(&mut app, CENTRE + Vec2::new(30.0, -10.0));
        step(&mut app);

        assert_eq!(
            window_position(&mut app),
            WindowPosition::At(IVec2::new(130, 190)),
            "the window must follow the cursor in physical pixels"
        );
        assert!(app.world().resource::<AnimStateMachine>().dragging);
        assert!(app.world().resource::<PointerState>().is_dragging());

        release_left(&mut app);
        step(&mut app);

        assert!(
            app.world().resource::<Collected>().0.is_empty(),
            "a drag must not also pet the pet"
        );
        assert!(!app.world().resource::<AnimStateMachine>().dragging);
    }

    #[test]
    fn drag_accumulates_across_frames() {
        let mut app = harness();
        set_cursor(&mut app, CENTRE);
        press_left(&mut app);
        step(&mut app);

        for _ in 0..3 {
            set_cursor(&mut app, CENTRE + Vec2::new(10.0, 5.0));
            step(&mut app);
        }

        assert_eq!(
            window_position(&mut app),
            WindowPosition::At(IVec2::new(130, 215)),
            "three 10×5 steps from the same grab point"
        );
    }

    #[test]
    fn movement_below_the_threshold_is_still_a_click() {
        let mut app = harness();
        set_cursor(&mut app, CENTRE);
        press_left(&mut app);
        step(&mut app);

        set_cursor(&mut app, CENTRE + Vec2::new(2.0, 1.0));
        step(&mut app);
        release_left(&mut app);
        step(&mut app);

        assert_eq!(app.world().resource::<Collected>().0, vec![PetCommand::Pet]);
        assert!(matches!(
            window_position(&mut app),
            WindowPosition::Automatic
        ));
    }

    #[test]
    fn click_on_the_transparent_margin_is_ignored() {
        let mut app = harness();
        // (10, 10) is inside the 300 px window but outside the 210 px sprite.
        set_cursor(&mut app, Vec2::splat(10.0));

        press_left(&mut app);
        step(&mut app);
        set_cursor(&mut app, Vec2::new(60.0, 60.0));
        step(&mut app);
        release_left(&mut app);
        step(&mut app);

        assert!(
            app.world().resource::<Collected>().0.is_empty(),
            "the overlay margin must not pet the pet"
        );
        assert!(matches!(
            window_position(&mut app),
            WindowPosition::Automatic
        ));
    }

    #[test]
    fn right_click_toggles_the_menu_at_the_cursor() {
        let mut app = harness();
        set_cursor(&mut app, Vec2::new(120.0, 90.0));

        app.world_mut()
            .resource_mut::<ButtonInput<MouseButton>>()
            .press(MouseButton::Right);
        step(&mut app);

        let menu = app.world().resource::<MenuState>();
        assert!(menu.visible);
        assert_eq!(menu.anchor, Vec2::new(120.0, 90.0));

        app.world_mut()
            .resource_mut::<ButtonInput<MouseButton>>()
            .release(MouseButton::Right);
        step(&mut app);
        app.world_mut()
            .resource_mut::<ButtonInput<MouseButton>>()
            .press(MouseButton::Right);
        step(&mut app);

        assert!(!app.world().resource::<MenuState>().visible);
    }

    #[test]
    fn left_click_outside_an_open_menu_dismisses_it() {
        let mut app = harness();
        app.world_mut().resource_mut::<MenuState>().visible = true;
        set_cursor(&mut app, CENTRE);

        press_left(&mut app);
        step(&mut app);
        release_left(&mut app);
        step(&mut app);

        assert!(!app.world().resource::<MenuState>().visible);
        assert!(
            app.world().resource::<Collected>().0.is_empty(),
            "the dismissing click must be consumed, not forwarded to the pet"
        );
    }

    #[test]
    fn drag_without_a_known_anchor_never_panics() {
        let mut app = harness();
        app.world_mut().resource_mut::<WindowAnchor>().physical = None;
        set_cursor(&mut app, CENTRE);

        press_left(&mut app);
        step(&mut app);
        set_cursor(&mut app, CENTRE + Vec2::splat(40.0));
        step(&mut app);

        assert!(matches!(
            window_position(&mut app),
            WindowPosition::Automatic
        ));
        assert!(
            app.world().resource::<AnimStateMachine>().dragging,
            "the drag pose still engages; only the move is skipped"
        );
    }

    /// Give the pet a real texture whose every pixel has the given alpha.
    fn set_sprite_alpha(app: &mut App, alpha: u8) {
        use bevy::asset::RenderAssetUsages;
        use bevy::render::render_resource::{Extent3d, TextureDimension, TextureFormat};

        const SIZE: u32 = 64;
        let image = Image::new(
            Extent3d {
                width: SIZE,
                height: SIZE,
                depth_or_array_layers: 1,
            },
            TextureDimension::D2,
            vec![alpha; (SIZE * SIZE * 4) as usize],
            TextureFormat::Rgba8UnormSrgb,
            RenderAssetUsages::default(),
        );
        let handle = app.world_mut().resource_mut::<Assets<Image>>().add(image);
        let mut sprites = app
            .world_mut()
            .query_filtered::<&mut Sprite, With<FramePlayer>>();
        let world = app.world_mut();
        sprites.single_mut(world).expect("sprite exists").image = handle;
    }

    fn click_centre(app: &mut App) -> Vec<PetCommand> {
        set_cursor(app, CENTRE);
        press_left(app);
        step(app);
        release_left(app);
        step(app);
        app.world().resource::<Collected>().0.clone()
    }

    #[test]
    fn fully_transparent_pixels_are_not_clickable() {
        let mut app = harness();
        set_sprite_alpha(&mut app, 0);
        assert!(
            click_centre(&mut app).is_empty(),
            "a transparent pixel inside the bounding box must not pet the pet"
        );
    }

    #[test]
    fn opaque_pixels_are_clickable() {
        let mut app = harness();
        set_sprite_alpha(&mut app, 255);
        assert_eq!(click_centre(&mut app), vec![PetCommand::Pet]);
    }
}
