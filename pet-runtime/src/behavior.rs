//! Autonomous behaviour.
//!
//! Every [`BEHAVIOR_INTERVAL_SECS`] the pet picks a random animation **from the
//! set that was actually loaded** and plays it, keeping the runtime
//! body-type-agnostic ("use whatever animations are available").
//!
//! The trigger condition is "the pet is resting", i.e. no action is playing and
//! it is not being dragged. It deliberately does *not* require the base to be
//! `Idle`: a pet whose base drifted to `Sleepy` / `Hungry` would otherwise stop
//! behaving autonomously for the rest of the session.

use std::time::SystemTime;

use bevy::prelude::*;

use crate::animation::{AnimState, AnimStateMachine, AnimationAssets};
use crate::config::{BEHAVIOR_FIRST_DELAY_SECS, BEHAVIOR_INTERVAL_SECS, LOOP_ACTION_SECS};

/// System set covering autonomous behaviour.
#[derive(SystemSet, Debug, Clone, PartialEq, Eq, Hash)]
pub struct BehaviorSystems;

// ---------------------------------------------------------------------------
// Resource
// ---------------------------------------------------------------------------

/// Counts down to the next random behaviour trigger.
#[derive(Resource)]
pub struct BehaviorTimer {
    pub timer: Timer,
    /// xorshift64 PRNG state.
    pub seed: u64,
}

/// Seed the PRNG from the wall clock so autonomous behaviour differs each run.
fn time_seed() -> u64 {
    let nanos = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .map(|d| d.as_nanos() as u64)
        .unwrap_or(0xDEAD_BEEF_CAFE_BABE);
    if nanos == 0 {
        0x9E37_79B9_7F4A_7C15 // golden-ratio constant; non-zero
    } else {
        nanos
    }
}

impl Default for BehaviorTimer {
    fn default() -> Self {
        Self {
            timer: Timer::from_seconds(BEHAVIOR_FIRST_DELAY_SECS, TimerMode::Once),
            seed: time_seed(),
        }
    }
}

// ---------------------------------------------------------------------------
// PRNG helpers (xorshift64 — no external crate needed at runtime)
// ---------------------------------------------------------------------------

fn xorshift64(state: &mut u64) -> u64 {
    let mut x = *state;
    x ^= x << 13;
    x ^= x >> 7;
    x ^= x << 17;
    *state = x;
    x
}

/// Pick a random element from `candidates` using the xorshift PRNG.
fn random_state(candidates: &[AnimState], seed: &mut u64) -> AnimState {
    if candidates.is_empty() {
        return AnimState::Idle;
    }
    candidates[(xorshift64(seed) as usize) % candidates.len()]
}

/// Return a random duration in `[min, max)` seconds.
fn random_duration(min: f32, max: f32, seed: &mut u64) -> f32 {
    let t = (xorshift64(seed) as f64 / u64::MAX as f64) as f32;
    min + t * (max - min)
}

/// Whether the pet is resting and may start an autonomous action.
///
/// Pure predicate so the (previously deadlock-prone) rule is unit-testable.
pub fn is_resting(sm: &AnimStateMachine) -> bool {
    !sm.dragging && sm.action.is_none()
}

/// Candidate animations for autonomous play, in a deterministic order.
pub fn candidates(assets: &AnimationAssets) -> Vec<AnimState> {
    let mut states: Vec<AnimState> = assets
        .available
        .iter()
        .copied()
        .filter(AnimState::is_autonomous_candidate)
        .collect();
    // `HashSet` iteration order is unspecified; sort by label so the candidate
    // list (and therefore tests) are reproducible.
    states.sort_unstable_by_key(|state| state.label());
    states
}

// ---------------------------------------------------------------------------
// Plugin & system
// ---------------------------------------------------------------------------

/// Registers autonomous behaviour.
pub struct BehaviorPlugin;

impl Plugin for BehaviorPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<BehaviorTimer>()
            .add_systems(Update, random_behavior.in_set(BehaviorSystems));
    }
}

/// Periodically trigger a random action animation from the available set.
pub fn random_behavior(
    time: Res<Time>,
    mut behavior: ResMut<BehaviorTimer>,
    mut sm: ResMut<AnimStateMachine>,
    assets: Res<AnimationAssets>,
) {
    behavior.timer.tick(time.delta());

    if !behavior.timer.just_finished() {
        return;
    }

    // Schedule the next trigger.
    let (min, max) = BEHAVIOR_INTERVAL_SECS;
    let next = random_duration(min, max, &mut behavior.seed);
    behavior
        .timer
        .set_duration(std::time::Duration::from_secs_f32(next));
    behavior.timer.reset();

    if !is_resting(&sm) {
        return;
    }

    let candidates = candidates(&assets);
    if candidates.is_empty() {
        return;
    }

    let chosen = random_state(&candidates, &mut behavior.seed);
    let duration = assets.action_duration(chosen, LOOP_ACTION_SECS);
    info!("Behavior: playing {:?} (duration={:?})", chosen, duration);
    sm.play_action(chosen, duration);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::animation::SpriteAnimation;
    use std::collections::{HashMap, HashSet};

    fn assets(states: &[AnimState]) -> AnimationAssets {
        let mut animations: HashMap<AnimState, SpriteAnimation> = HashMap::new();
        for &state in states {
            animations.insert(
                state,
                SpriteAnimation {
                    frames: Vec::new(),
                    fps: 12.0,
                    loop_anim: true,
                    default_duration: Some(2.0),
                },
            );
        }
        let available: HashSet<AnimState> = animations.keys().copied().collect();
        AnimationAssets {
            animations,
            available,
        }
    }

    #[test]
    fn resting_ignores_the_mood_base() {
        let mut sm = AnimStateMachine::default();
        assert!(is_resting(&sm));

        // A Sleepy / Hungry base used to dead-lock autonomous behaviour.
        sm.set_base(AnimState::Sleepy);
        assert!(is_resting(&sm), "a mood base must not block behaviour");

        sm.play_action(AnimState::Dance, Some(1.0));
        assert!(!is_resting(&sm), "an action in flight blocks behaviour");

        sm.action = None;
        sm.dragging = true;
        assert!(!is_resting(&sm), "dragging blocks behaviour");
    }

    #[test]
    fn candidates_exclude_bases_sleep_and_drag() {
        let assets = assets(&[
            AnimState::Idle,
            AnimState::Sleepy,
            AnimState::Hungry,
            AnimState::Sleep,
            AnimState::Drag,
            AnimState::Dance,
            AnimState::Wave,
        ]);
        assert_eq!(candidates(&assets), vec![AnimState::Dance, AnimState::Wave]);
    }

    #[test]
    fn candidates_are_empty_for_a_single_sheet_pet() {
        let assets = assets(&[AnimState::Idle]);
        assert!(candidates(&assets).is_empty());
    }

    #[test]
    fn random_state_is_deterministic_for_a_seed_and_stays_in_range() {
        let pool = vec![AnimState::Dance, AnimState::Wave, AnimState::Yawn];
        let mut seed = 0x1234_5678_9ABC_DEF0;
        let first: Vec<AnimState> = (0..16).map(|_| random_state(&pool, &mut seed)).collect();
        assert!(first.iter().all(|state| pool.contains(state)));

        let mut seed = 0x1234_5678_9ABC_DEF0;
        let second: Vec<AnimState> = (0..16).map(|_| random_state(&pool, &mut seed)).collect();
        assert_eq!(first, second, "same seed must replay the same sequence");
    }

    #[test]
    fn random_state_handles_an_empty_pool() {
        let mut seed = 7;
        assert_eq!(random_state(&[], &mut seed), AnimState::Idle);
    }

    #[test]
    fn random_duration_stays_within_bounds() {
        let mut seed = 99;
        let (min, max) = BEHAVIOR_INTERVAL_SECS;
        for _ in 0..64 {
            let value = random_duration(min, max, &mut seed);
            assert!((min..=max).contains(&value), "{value} out of range");
        }
    }
}
