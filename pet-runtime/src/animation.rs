//! Animation layer: the [`AnimState`] taxonomy, sprite-sheet playback and the
//! three-layer state machine. This module knows **nothing** about input or UI —
//! it only exposes state to mutate ([`AnimStateMachine`]) and data to render
//! ([`AnimationAssets`]).
//!
//! Design principle: the runtime never hard-codes `body_type` logic.
//! "Use whatever animations are available" — the generator manifest determines
//! which [`AnimState`] variants have frame data, and every consumer intersects
//! its choices with [`AnimationAssets::available`].
//!
//! ## State-machine model
//!
//! Render priority is `drag > action > base`:
//!
//! * `base` — the resting, mood-driven state (guaranteed ∈ `available`);
//! * `action` — an optional one-shot overlay ([`ActionSlot`]) that either counts
//!   down a duration (looping / timed actions) or plays until the
//!   [`FramePlayer`] reports `finished` (non-looping one-shots), with a
//!   watchdog so a corrupt sheet can never dead-lock the machine;
//! * `dragging` — a boolean overlay owned by the interaction layer; it forces
//!   the `Drag` pose while held and has no frame data of its own.

use bevy::prelude::*;
use std::collections::{HashMap, HashSet};

use crate::config::ACTION_WATCHDOG_SECS;

// ---------------------------------------------------------------------------
// AnimState — full enumeration across all body types
// ---------------------------------------------------------------------------

/// Every animation the runtime *can* play. A given pet only ships a subset
/// (determined by its `body_type` in the generator manifest).
///
/// `allow(dead_code)`: variants are constructed by the generator-inserted
/// `SPRITE_SHEETS` entries (data-driven), so body-type-specific variants stay
/// unreferenced in template code until the generator patches them in.
#[allow(dead_code)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default)]
pub enum AnimState {
    // -- universal ----------------------------------------------------------
    #[default]
    Idle,
    Happy,
    Sleep,
    Drag,

    // -- humanoid -----------------------------------------------------------
    Sleepy,
    Hungry,
    Dance,
    Wave,
    Yawn,
    Stretch,
    LookAround,

    // -- quadruped ----------------------------------------------------------
    TailWag,
    Walk,
    Run,
    Sit,
    Pounce,
    TiltHead,
    Scratch,

    // -- limbless -----------------------------------------------------------
    Bounce,
    Squish,
    StretchVertical,
    Float,
    Spin,
    Wobble,

    // -- object -------------------------------------------------------------
    Glow,
    Shake,
    Tilt,
    BounceSmall,
    Sparkle,
}

/// Display order for deliberate actions (context menu, tray, future hotkeys).
///
/// Only states in this list are offered as user-triggerable actions; the list
/// is intersected with [`AnimationAssets::available`] so it stays
/// body-type-agnostic. Extending the taxonomy = add the variant above, add it
/// here, and (if it is a resting pose) teach [`AnimState::is_mood_base`].
pub const ACTION_ORDER: &[AnimState] = &[
    AnimState::Dance,
    AnimState::Wave,
    AnimState::Yawn,
    AnimState::Stretch,
    AnimState::LookAround,
    AnimState::TailWag,
    AnimState::Walk,
    AnimState::Run,
    AnimState::Sit,
    AnimState::Pounce,
    AnimState::TiltHead,
    AnimState::Scratch,
    AnimState::Bounce,
    AnimState::Squish,
    AnimState::StretchVertical,
    AnimState::Float,
    AnimState::Spin,
    AnimState::Wobble,
    AnimState::Glow,
    AnimState::Shake,
    AnimState::Tilt,
    AnimState::BounceSmall,
    AnimState::Sparkle,
];

impl AnimState {
    /// Human-readable label (ASCII only — see `docs/standards/RUNTIME_UX.md`:
    /// the embedded default font covers U+0020..U+007E exclusively).
    pub fn label(&self) -> &'static str {
        match self {
            Self::Idle => "Idle",
            Self::Happy => "Happy",
            Self::Sleep => "Sleep",
            Self::Drag => "Drag",
            Self::Sleepy => "Sleepy",
            Self::Hungry => "Hungry",
            Self::Dance => "Dance",
            Self::Wave => "Wave",
            Self::Yawn => "Yawn",
            Self::Stretch => "Stretch",
            Self::LookAround => "Look",
            Self::TailWag => "Tail Wag",
            Self::Walk => "Walk",
            Self::Run => "Run",
            Self::Sit => "Sit",
            Self::Pounce => "Pounce",
            Self::TiltHead => "Tilt Head",
            Self::Scratch => "Scratch",
            Self::Bounce => "Bounce",
            Self::Squish => "Squish",
            Self::StretchVertical => "Stretch Up",
            Self::Float => "Float",
            Self::Spin => "Spin",
            Self::Wobble => "Wobble",
            Self::Glow => "Glow",
            Self::Shake => "Shake",
            Self::Tilt => "Tilt",
            Self::BounceSmall => "Bounce",
            Self::Sparkle => "Sparkle",
        }
    }

    /// Whether this state is a *resting* pose driven by mood rather than a
    /// deliberate action (never picked by the autonomous behaviour system).
    pub fn is_mood_base(&self) -> bool {
        matches!(self, Self::Idle | Self::Sleepy | Self::Hungry)
    }

    /// Whether the autonomous behaviour system may pick this state.
    ///
    /// Excludes resting poses (they are bases), `Sleep` (deliberate only) and
    /// `Drag` (no frame data of its own).
    pub fn is_autonomous_candidate(&self) -> bool {
        !self.is_mood_base() && !matches!(self, Self::Sleep | Self::Drag)
    }
}

// ---------------------------------------------------------------------------
// SpriteAnimation — one loaded sprite-sheet
// ---------------------------------------------------------------------------

/// A single sprite-sheet animation loaded from embedded PNG bytes.
///
/// Frames are pre-decoded on the CPU into individual `FRAME_SIZE²` textures,
/// avoiding GPU max-texture-size limits for very wide sprite sheets.
pub struct SpriteAnimation {
    /// Pre-decoded frame texture handles (one per frame).
    pub frames: Vec<Handle<Image>>,
    /// Playback speed in frames-per-second.
    pub fps: f32,
    /// Whether the animation loops or plays once.
    pub loop_anim: bool,
    /// Suggested playback duration in seconds (5th tuple element of the
    /// generator contract), or `None` when the sheet declares none.
    pub default_duration: Option<f32>,
}

impl SpriteAnimation {
    /// Total number of frames in this animation.
    pub fn frame_count(&self) -> u32 {
        self.frames.len() as u32
    }
}

// ---------------------------------------------------------------------------
// Resources
// ---------------------------------------------------------------------------

/// All loaded animations, keyed by state.
#[derive(Resource)]
pub struct AnimationAssets {
    /// Decoded animations, keyed by state.
    pub animations: HashMap<AnimState, SpriteAnimation>,
    /// The set of states that actually decoded successfully.
    ///
    /// Consumers (mood mapping, autonomous behaviour, menus) intersect with
    /// this set so the runtime stays body-type-agnostic.
    pub available: HashSet<AnimState>,
}

impl AnimationAssets {
    /// Resolve a safe duration for a deliberate action:
    /// * looping sheets are always timed (declared duration, else `fallback`)
    ///   so they revert to base instead of playing forever;
    /// * non-looping sheets play to completion (`None`).
    ///
    /// Unknown states get `Some(fallback)` — they will render the `Idle`
    /// fallback frames, so a countdown is the only safe exit.
    pub fn action_duration(&self, state: AnimState, fallback: f32) -> Option<f32> {
        match self.animations.get(&state) {
            Some(anim) if anim.loop_anim => Some(anim.default_duration.unwrap_or(fallback)),
            Some(_) => None,
            None => Some(fallback),
        }
    }
}

/// A one-shot action overlay with an optional countdown.
#[derive(Clone, Copy, Debug)]
pub struct ActionSlot {
    /// The animation to render while this slot is active.
    pub state: AnimState,
    /// Remaining duration in seconds.
    /// * `None` — play until the [`FramePlayer`] reports `finished`
    ///   (non-looping one-shots such as Wave/Yawn);
    /// * `Some(t)` — count down `t` seconds, then revert to base (looping or
    ///   deliberately timed actions such as Dance/Happy/Sleep).
    pub remaining: Option<f32>,
    /// Seconds this slot has been active — watchdog against sheets that never
    /// report `finished`.
    pub elapsed: f32,
}

/// High-level animation state machine.
///
/// Render priority is `drag > action > base` (see [`Self::effective`]).
#[derive(Resource, Default)]
pub struct AnimStateMachine {
    /// Resting, mood-driven base state (callers intersect with `available`).
    pub base: AnimState,
    /// Optional one-shot overlay (interaction / menu / autonomous behaviour).
    pub action: Option<ActionSlot>,
    /// Drag overlay flag (highest priority, owned by the interaction layer).
    pub dragging: bool,
}

impl AnimStateMachine {
    /// The state that should actually be rendered right now.
    pub fn effective(&self) -> AnimState {
        if self.dragging {
            return AnimState::Drag;
        }
        self.action.map(|a| a.state).unwrap_or(self.base)
    }

    /// Request a one-shot action animation.
    ///
    /// `duration`:
    /// * `Some(t)` — revert to base after `t` seconds. **Required** for
    ///   looping animations so they never play forever;
    /// * `None` — revert when the non-looping animation finishes (bounded by
    ///   [`ACTION_WATCHDOG_SECS`]).
    pub fn play_action(&mut self, state: AnimState, duration: Option<f32>) {
        self.action = Some(ActionSlot {
            state,
            remaining: duration,
            elapsed: 0.0,
        });
    }

    /// Set the base (looping) state and clear any action.
    pub fn set_base(&mut self, state: AnimState) {
        self.base = state;
        self.action = None;
    }

    /// Advance the active action by `dt` seconds.
    ///
    /// `frame_finished` signals that the [`FramePlayer`] reached the end of a
    /// non-looping animation. Exposed as a pure method so the timing logic is
    /// unit-testable without a full Bevy `App`.
    pub fn tick_action(&mut self, dt: f32, frame_finished: bool) {
        let Some(slot) = self.action.as_mut() else {
            return;
        };
        slot.elapsed += dt;
        let clear = match slot.remaining {
            Some(ref mut remaining) => {
                *remaining -= dt;
                *remaining <= 0.0
            }
            // Untimed actions end with their frames; the watchdog guarantees an
            // exit even if `finished` never arrives.
            None => frame_finished || slot.elapsed >= ACTION_WATCHDOG_SECS,
        };
        if clear {
            self.action = None;
        }
    }
}

// ---------------------------------------------------------------------------
// Components
// ---------------------------------------------------------------------------

/// Per-entity frame-animation player.
#[derive(Component)]
pub struct FramePlayer {
    /// The AnimState currently being rendered.
    pub current: AnimState,
    /// Accumulator timer for frame advancement.
    pub timer: Timer,
    /// Current frame index within the sprite-sheet.
    pub frame_index: usize,
    /// Set to `true` when a non-looping animation reaches its last frame.
    pub finished: bool,
}

impl Default for FramePlayer {
    fn default() -> Self {
        Self {
            current: AnimState::Idle,
            timer: Timer::from_seconds(1.0 / 8.0, TimerMode::Repeating),
            frame_index: 0,
            finished: false,
        }
    }
}

// ---------------------------------------------------------------------------
// Plugin
// ---------------------------------------------------------------------------

/// System set covering animation playback and action bookkeeping.
#[derive(SystemSet, Debug, Clone, PartialEq, Eq, Hash)]
pub struct AnimationSystems;

/// Registers the animation state machine and its playback systems.
pub struct AnimationPlugin;

impl Plugin for AnimationPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<AnimStateMachine>().add_systems(
            Update,
            // Chained so `finished` reflects the current frame before the
            // action countdown inspects it.
            (animate_sprite, tick_action_duration)
                .chain()
                .in_set(AnimationSystems),
        );
    }
}

// ---------------------------------------------------------------------------
// Systems
// ---------------------------------------------------------------------------

/// Advance sprite-sheet frames and sync the `Sprite` texture handle.
///
/// Fallback logic: if the effective state has no loaded animation data, fall
/// back to `Idle`. Frame advancement is frozen while dragging **only when the
/// pet actually ships a `Drag` sheet** — otherwise the fallback animation keeps
/// playing so a dragged pet never looks frozen.
pub fn animate_sprite(
    time: Res<Time>,
    assets: Res<AnimationAssets>,
    sm: Res<AnimStateMachine>,
    mut query: Query<(&mut FramePlayer, &mut Sprite)>,
) {
    let effective = sm.effective();
    let freeze = sm.dragging && assets.available.contains(&AnimState::Drag);

    for (mut player, mut sprite) in &mut query {
        // Detect state change → reset player.
        if player.current != effective {
            player.current = effective;
            player.frame_index = 0;
            player.finished = false;
        }

        // Resolve animation data with graceful fallback.
        let Some(anim) = assets
            .animations
            .get(&effective)
            .or_else(|| assets.animations.get(&AnimState::Idle))
        else {
            continue; // No animation data at all — keep the last frame.
        };

        // Reconfigure timer if fps changed.
        let target_duration = 1.0 / anim.fps.max(0.1);
        if (player.timer.duration().as_secs_f32() - target_duration).abs() > f32::EPSILON {
            player
                .timer
                .set_duration(std::time::Duration::from_secs_f32(target_duration));
        }

        if !player.finished && !freeze {
            player.timer.tick(time.delta());

            if player.timer.just_finished() {
                player.frame_index += 1;

                if player.frame_index >= anim.frame_count() as usize {
                    if anim.loop_anim {
                        player.frame_index = 0;
                    } else {
                        player.frame_index = anim.frame_count().saturating_sub(1) as usize;
                        player.finished = true;
                    }
                }
            }
        }

        // Swap the sprite's image handle to the current frame texture.
        if let Some(frame) = anim.frames.get(player.frame_index) {
            sprite.image = frame.clone();
        }
    }
}

/// Count down the active action and clear it when it should revert to base.
pub fn tick_action_duration(
    time: Res<Time>,
    mut sm: ResMut<AnimStateMachine>,
    query: Query<&FramePlayer>,
) {
    if sm.action.is_none() {
        return;
    }
    let frame_finished = query.iter().any(|player| player.finished);
    sm.tick_action(time.delta_secs(), frame_finished);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::pet::{resolve_base_for_mood, Mood};

    #[test]
    fn zero_duration_action_reverts_to_base_on_tick() {
        let mut sm = AnimStateMachine::default();
        sm.play_action(AnimState::Happy, Some(0.0));
        assert_eq!(sm.effective(), AnimState::Happy);

        sm.tick_action(0.016, false);
        assert!(sm.action.is_none(), "elapsed action must be cleared");
        assert_eq!(sm.effective(), AnimState::Idle);
    }

    #[test]
    fn timed_action_counts_down_then_reverts() {
        let mut sm = AnimStateMachine::default();
        sm.play_action(AnimState::Dance, Some(1.0));

        sm.tick_action(0.5, false);
        assert_eq!(sm.effective(), AnimState::Dance, "still within duration");

        sm.tick_action(0.6, false);
        assert!(sm.action.is_none(), "duration elapsed → revert");
        assert_eq!(sm.effective(), AnimState::Idle);
    }

    #[test]
    fn untimed_action_clears_when_frames_finish() {
        let mut sm = AnimStateMachine::default();
        sm.play_action(AnimState::Wave, None);

        sm.tick_action(0.5, false);
        assert_eq!(sm.effective(), AnimState::Wave, "frames not finished yet");

        sm.tick_action(0.5, true);
        assert!(sm.action.is_none(), "FramePlayer finished → revert");
    }

    #[test]
    fn untimed_action_is_bounded_by_watchdog() {
        let mut sm = AnimStateMachine::default();
        sm.play_action(AnimState::Wave, None);

        // `finished` never arrives (corrupt sheet): the watchdog must save us.
        for _ in 0..((ACTION_WATCHDOG_SECS / 0.5) as usize) {
            sm.tick_action(0.5, false);
        }
        assert!(sm.action.is_none(), "watchdog must clear a stuck action");
    }

    #[test]
    fn dragging_has_highest_priority() {
        let mut sm = AnimStateMachine::default();
        sm.set_base(AnimState::Sleepy);
        sm.play_action(AnimState::Happy, Some(5.0));

        sm.dragging = true;
        assert_eq!(sm.effective(), AnimState::Drag, "drag overrides action");

        sm.dragging = false;
        assert_eq!(sm.effective(), AnimState::Happy, "action over base");
    }

    fn assets_with(states: &[(AnimState, bool, Option<f32>)]) -> AnimationAssets {
        let mut animations = HashMap::new();
        for &(state, loop_anim, default_duration) in states {
            animations.insert(
                state,
                SpriteAnimation {
                    frames: Vec::new(),
                    fps: 12.0,
                    loop_anim,
                    default_duration,
                },
            );
        }
        let available = animations.keys().copied().collect();
        AnimationAssets {
            animations,
            available,
        }
    }

    #[test]
    fn action_duration_times_looping_sheets_and_frees_one_shots() {
        let assets = assets_with(&[
            (AnimState::Dance, true, Some(3.0)),
            (AnimState::Glow, true, None),
            (AnimState::Wave, false, Some(2.0)),
        ]);

        assert_eq!(assets.action_duration(AnimState::Dance, 9.0), Some(3.0));
        assert_eq!(
            assets.action_duration(AnimState::Glow, 9.0),
            Some(9.0),
            "looping sheet without a declared duration falls back"
        );
        assert_eq!(
            assets.action_duration(AnimState::Wave, 9.0),
            None,
            "non-looping sheet plays to completion"
        );
        assert_eq!(
            assets.action_duration(AnimState::Spin, 9.0),
            Some(9.0),
            "unknown state must be timed"
        );
    }

    #[test]
    fn taxonomy_separates_bases_from_actions() {
        assert!(AnimState::Idle.is_mood_base());
        assert!(AnimState::Sleepy.is_mood_base());
        assert!(!AnimState::Dance.is_mood_base());

        assert!(AnimState::Dance.is_autonomous_candidate());
        assert!(!AnimState::Sleep.is_autonomous_candidate());
        assert!(!AnimState::Drag.is_autonomous_candidate());
        assert!(!AnimState::Idle.is_autonomous_candidate());
    }

    #[test]
    fn action_order_contains_no_bases_and_no_duplicates() {
        let mut seen = HashSet::new();
        for state in ACTION_ORDER {
            assert!(
                !state.is_mood_base(),
                "{state:?} is a mood base and must not be offered as an action"
            );
            assert!(
                seen.insert(*state),
                "duplicate entry {state:?} in ACTION_ORDER"
            );
        }
    }

    #[test]
    fn availability_intersection_keeps_idle_when_anim_missing() {
        let available: HashSet<AnimState> = [AnimState::Idle, AnimState::Happy, AnimState::TailWag]
            .into_iter()
            .collect();
        assert_eq!(
            resolve_base_for_mood(Mood::Sleepy, &available),
            AnimState::Idle,
            "missing Sleepy must fall back to Idle"
        );
    }

    #[test]
    fn availability_intersection_uses_anim_when_present() {
        let available: HashSet<AnimState> =
            [AnimState::Idle, AnimState::Sleepy].into_iter().collect();
        assert_eq!(
            resolve_base_for_mood(Mood::Sleepy, &available),
            AnimState::Sleepy
        );
    }
}
