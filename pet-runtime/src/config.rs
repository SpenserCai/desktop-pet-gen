//! Central tuning surface for the runtime.
//!
//! Every magic number that affects *feel* (window geometry, interaction
//! thresholds, action durations, vital economy) lives here so tuning never
//! requires hunting through systems. Modules import from here instead of
//! declaring private constants.
//!
//! Conventions:
//! * lengths are **logical** pixels (points) unless the name says `PHYSICAL`;
//! * durations are seconds;
//! * vitals are on a `0.0..=100.0` scale.

// ---------------------------------------------------------------------------
// Window & sprite geometry
// ---------------------------------------------------------------------------

/// Side length of the (square) transparent overlay window, logical px.
///
/// Must be large enough to host the action menu and the HUD without clipping:
/// the menu is `MENU_WIDTH` wide and up to
/// `MAX_MENU_ITEMS * MENU_ITEM_HEIGHT` tall.
pub const WINDOW_SIZE: f32 = 300.0;

/// On-screen size of the pet sprite, logical px (square).
pub const SPRITE_SIZE: f32 = 210.0;

/// Margin from the right screen edge used for the initial window placement.
pub const SPAWN_MARGIN_RIGHT: f32 = 40.0;

/// Margin from the bottom screen edge (leaves room for the macOS Dock /
/// Windows taskbar) used for the initial window placement.
pub const SPAWN_MARGIN_BOTTOM: f32 = 90.0;

// ---------------------------------------------------------------------------
// Pointer interaction
// ---------------------------------------------------------------------------

/// Cursor travel (logical px) that promotes a left press from "click" to
/// "drag". Below it a release is treated as a pet/stroke interaction.
pub const DRAG_THRESHOLD: f32 = 4.0;

/// Alpha threshold for the sprite hit test: pixels below this are treated as
/// "not the pet", so clicks on the transparent margins never pet it.
pub const ALPHA_HIT_THRESHOLD: f32 = 0.08;

/// Squash-and-stretch intensity per logical px of per-frame drag speed.
pub const SQUASH_PER_SPEED: f32 = 0.006;

/// Upper bound for the squash-and-stretch deformation (0.2 = ±20 %).
pub const SQUASH_MAX: f32 = 0.2;

// ---------------------------------------------------------------------------
// Action durations
// ---------------------------------------------------------------------------

/// Fallback duration for a *looping* one-shot action whose sheet declares no
/// `duration_secs`. Looping actions must always be timed, otherwise they never
/// revert to the base state.
pub const LOOP_ACTION_SECS: f32 = 3.0;

/// Duration of the `Happy` reaction used for petting / feeding / playing when
/// the sheet declares no `duration_secs`.
pub const HAPPY_SECS: f32 = 1.5;

/// Duration of a deliberate `Sleep` action (it is never a permanent base).
pub const SLEEP_SECS: f32 = 10.0;

/// Watchdog for untimed (frame-driven) actions: if a non-looping animation
/// never reports `finished` (corrupt sheet, zero frames), the action is
/// dropped after this many seconds so the pet can never dead-lock.
pub const ACTION_WATCHDOG_SECS: f32 = 20.0;

/// Autonomous behaviour: seconds before the first random action.
pub const BEHAVIOR_FIRST_DELAY_SECS: f32 = 10.0;

/// Autonomous behaviour: inclusive-exclusive range between random actions.
pub const BEHAVIOR_INTERVAL_SECS: (f32, f32) = (15.0, 30.0);

// ---------------------------------------------------------------------------
// Vital economy
// ---------------------------------------------------------------------------

/// Energy drained per minute (full → empty in ≈100 min).
pub const ENERGY_DECAY_PER_MIN: f32 = 1.0;
/// Happiness drained per minute.
pub const HAPPINESS_DECAY_PER_MIN: f32 = 1.5;
/// Hunger *growth* per minute (high hunger = bad).
pub const HUNGER_GROWTH_PER_MIN: f32 = 2.0;

/// Happiness gained by a single pet/stroke interaction.
pub const PET_HAPPINESS_GAIN: f32 = 10.0;
/// Happiness gained by the `Play` menu action.
pub const PLAY_HAPPINESS_GAIN: f32 = 20.0;
/// Hunger removed by the `Feed` menu action.
pub const FEED_HUNGER_RELIEF: f32 = 30.0;
/// Energy restored by the `Sleep` menu action.
pub const SLEEP_ENERGY_RESTORE: f32 = 40.0;

// ---------------------------------------------------------------------------
// UI
// ---------------------------------------------------------------------------

/// Width of the context menu, logical px.
pub const MENU_WIDTH: f32 = 128.0;

/// Height of a single menu row, logical px (used for placement estimates).
pub const MENU_ITEM_HEIGHT: f32 = 21.0;

/// Hard cap on menu rows so an exotic action set can never overflow the
/// window (the surplus is dropped, never clipped).
pub const MAX_MENU_ITEMS: usize = 12;

/// Padding between the menu and the window edge when clamping, logical px.
pub const MENU_EDGE_PADDING: f32 = 6.0;

/// How long a toast notification stays on screen, seconds.
pub const TOAST_SECS: f32 = 2.6;

/// Fade-out tail of a toast, seconds (must be < [`TOAST_SECS`]).
pub const TOAST_FADE_SECS: f32 = 0.6;

/// Maximum simultaneously visible toasts (oldest is dropped first).
pub const MAX_TOASTS: usize = 3;
