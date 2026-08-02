//! Pet vitals: mood tracking and stat decay over time.
//!
//! All state is purely in-memory: nothing is ever persisted to disk, so the pet
//! resets every time the program starts (by design — zero file writes).
//!
//! Decay rates live in [`crate::config`] and are tuned for a *companion*
//! rhythm: slow enough that a pet left alone for an hour is still clearly
//! alive, fast enough that regular interaction visibly matters.

use std::collections::HashSet;

use bevy::prelude::*;

use crate::animation::{AnimState, AnimStateMachine, AnimationAssets};
use crate::config::{ENERGY_DECAY_PER_MIN, HAPPINESS_DECAY_PER_MIN, HUNGER_GROWTH_PER_MIN};

// ---------------------------------------------------------------------------
// Mood
// ---------------------------------------------------------------------------

/// Coarse mood bucket derived from the pet's vital stats.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum Mood {
    #[default]
    Idle,
    Happy,
    Sleepy,
    Hungry,
}

impl Mood {
    /// Map mood to a suggested AnimState (may not exist for every pet).
    pub fn suggested_anim(&self) -> AnimState {
        match self {
            Self::Idle => AnimState::Idle,
            Self::Happy => AnimState::Happy,
            Self::Sleepy => AnimState::Sleepy,
            Self::Hungry => AnimState::Hungry,
        }
    }
}

/// Resolve the base [`AnimState`] for a `mood`, intersecting with the set of
/// animations actually available.
///
/// Body-type-agnostic: only `Sleepy` / `Hungry` moods drive the base away from
/// `Idle`, and only if that animation was decoded. A quadruped / limbless /
/// object pet has no `Sleepy` / `Hungry` sheets, so its base stays `Idle`.
/// `Happy` is expressed through one-shot actions, never as a base.
pub fn resolve_base_for_mood(mood: Mood, available: &HashSet<AnimState>) -> AnimState {
    let suggested = mood.suggested_anim();
    match suggested {
        AnimState::Sleepy | AnimState::Hungry => {
            if available.contains(&suggested) {
                suggested
            } else {
                AnimState::Idle
            }
        }
        _ => AnimState::Idle,
    }
}

// ---------------------------------------------------------------------------
// Pet component
// ---------------------------------------------------------------------------

/// Core pet vitals. All values are in `[0.0, 100.0]`.
#[derive(Component)]
pub struct Pet {
    /// Energy — decreases over time; low energy → Sleepy mood.
    pub energy: f32,
    /// Happiness — boosted by interaction; decays slowly.
    pub happiness: f32,
    /// Hunger — *increases* over time; high hunger → Hungry mood.
    pub hunger: f32,
    /// Derived mood (recomputed on every change).
    pub mood: Mood,
}

impl Default for Pet {
    fn default() -> Self {
        Self {
            energy: 80.0,
            happiness: 70.0,
            hunger: 20.0,
            mood: Mood::Idle,
        }
    }
}

impl Pet {
    /// Recompute mood from current stats.
    pub fn recompute_mood(&mut self) {
        self.mood = if self.energy < 25.0 {
            Mood::Sleepy
        } else if self.hunger > 75.0 {
            Mood::Hungry
        } else if self.happiness > 70.0 {
            Mood::Happy
        } else {
            Mood::Idle
        };
    }

    /// Add (or remove, with a negative value) happiness, clamped and with the
    /// mood kept consistent.
    pub fn add_happiness(&mut self, delta: f32) {
        self.happiness = (self.happiness + delta).clamp(0.0, 100.0);
        self.recompute_mood();
    }

    /// Add (or remove) energy, clamped and with the mood kept consistent.
    pub fn add_energy(&mut self, delta: f32) {
        self.energy = (self.energy + delta).clamp(0.0, 100.0);
        self.recompute_mood();
    }

    /// Relieve hunger by `amount` (feeding), clamped and mood-consistent.
    pub fn relieve_hunger(&mut self, amount: f32) {
        self.hunger = (self.hunger - amount).clamp(0.0, 100.0);
        self.recompute_mood();
    }
}

// ---------------------------------------------------------------------------
// Plugin
// ---------------------------------------------------------------------------

/// Registers the vital-decay system.
pub struct PetPlugin;

impl Plugin for PetPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Update, decay_system);
    }
}

// ---------------------------------------------------------------------------
// Systems
// ---------------------------------------------------------------------------

/// Decay / grow vitals over time, update the derived mood, and hint the base
/// animation state.
///
/// The mood → base mapping is intersected with [`AnimationAssets::available`]
/// so pets whose body type lacks `Sleepy` / `Hungry` animations keep `Idle` as
/// base and remain autonomously active.
pub fn decay_system(
    time: Res<Time>,
    assets: Res<AnimationAssets>,
    mut query: Query<&mut Pet>,
    mut sm: ResMut<AnimStateMachine>,
) {
    let dt = time.delta_secs();

    for mut pet in &mut query {
        pet.energy = (pet.energy - ENERGY_DECAY_PER_MIN / 60.0 * dt).clamp(0.0, 100.0);
        pet.happiness = (pet.happiness - HAPPINESS_DECAY_PER_MIN / 60.0 * dt).clamp(0.0, 100.0);
        pet.hunger = (pet.hunger + HUNGER_GROWTH_PER_MIN / 60.0 * dt).clamp(0.0, 100.0);

        let old_mood = pet.mood;
        pet.recompute_mood();

        // Only re-base on mood change while no action is playing, so a one-shot
        // action is never clobbered mid-flight.
        if pet.mood != old_mood && sm.action.is_none() {
            let target = resolve_base_for_mood(pet.mood, &assets.available);
            if sm.base != target {
                sm.set_base(target);
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::PET_HAPPINESS_GAIN;

    #[test]
    fn mood_priority_is_energy_then_hunger_then_happiness() {
        let mut pet = Pet {
            energy: 10.0,
            happiness: 100.0,
            hunger: 100.0,
            mood: Mood::Idle,
        };
        pet.recompute_mood();
        assert_eq!(pet.mood, Mood::Sleepy, "low energy wins");

        pet.energy = 80.0;
        pet.recompute_mood();
        assert_eq!(pet.mood, Mood::Hungry, "then starvation");

        pet.hunger = 10.0;
        pet.recompute_mood();
        assert_eq!(pet.mood, Mood::Happy, "then happiness");

        pet.happiness = 40.0;
        pet.recompute_mood();
        assert_eq!(pet.mood, Mood::Idle);
    }

    #[test]
    fn vital_mutations_are_clamped() {
        let mut pet = Pet::default();
        pet.add_happiness(1_000.0);
        assert_eq!(pet.happiness, 100.0);
        pet.add_energy(-1_000.0);
        assert_eq!(pet.energy, 0.0);
        pet.relieve_hunger(1_000.0);
        assert_eq!(pet.hunger, 0.0);
    }

    #[test]
    fn happiness_gain_matches_the_configured_pet_reward() {
        let mut pet = Pet {
            happiness: 10.0,
            ..Default::default()
        };
        pet.add_happiness(PET_HAPPINESS_GAIN);
        assert_eq!(pet.happiness, 10.0 + PET_HAPPINESS_GAIN);
    }
}
