//! Achievements.
//!
//! Four achievements tracked purely in memory (nothing is persisted, so
//! progress resets on every launch — by design: zero file writes).
//!
//! Unlocks are reported by **returning the achievement name** instead of
//! printing, so the caller ([`crate::command::apply_commands`]) can surface
//! them through the toast bus. A GUI app started from Finder / Explorer has no
//! visible stdout, so on-screen feedback is the only feedback that counts.
//!
//! ## Body-type-agnostic design
//!
//! The "Dancer" achievement is driven by [`Achievements::register_action`],
//! which is aware of the decoded animation set:
//! * if the pet ships a `Dance` animation, only deliberate `Dance` triggers
//!   count (preserving the original spirit);
//! * otherwise **any** deliberate action counts, so every body type can unlock
//!   it.
//!
//! Only *user-initiated* actions are registered — the autonomous behaviour
//! system never calls into this module.

use std::collections::HashSet;

use bevy::prelude::*;

use crate::animation::AnimState;
use crate::command::Notice;
use crate::pet::Pet;

/// Healthy-stat threshold and streak duration for the Survivor achievement.
const SURVIVOR_THRESHOLD: f32 = 50.0;
const SURVIVOR_SECONDS: f32 = 300.0;

/// Petting count that unlocks "Pet Lover".
const PET_LOVER_COUNT: u32 = 10;
/// Deliberate-action count that unlocks "Dancer".
const DANCER_COUNT: u32 = 3;

/// Tracks progress toward every achievement.
#[derive(Resource, Default)]
pub struct Achievements {
    first_feed: bool,
    pet_count: u32,
    pet_lover: bool,
    action_count: u32,
    dancer: bool,
    survivor: bool,
    /// Seconds the pet has stayed healthy continuously.
    survivor_time: f32,
}

impl Achievements {
    /// Register a feeding. Returns the achievement name when it unlocks.
    pub fn register_feed(&mut self) -> Option<&'static str> {
        if self.first_feed {
            return None;
        }
        self.first_feed = true;
        Some("First Feed")
    }

    /// Register a pet/stroke. Returns the achievement name when it unlocks.
    pub fn register_pet(&mut self) -> Option<&'static str> {
        self.pet_count += 1;
        if self.pet_lover || self.pet_count < PET_LOVER_COUNT {
            return None;
        }
        self.pet_lover = true;
        Some("Pet Lover")
    }

    /// Register a deliberate action. Returns the achievement name on unlock.
    pub fn register_action(
        &mut self,
        state: AnimState,
        available: &HashSet<AnimState>,
    ) -> Option<&'static str> {
        let counts = if available.contains(&AnimState::Dance) {
            state == AnimState::Dance
        } else {
            true
        };
        if !counts {
            return None;
        }
        self.action_count += 1;
        if self.dancer || self.action_count < DANCER_COUNT {
            return None;
        }
        self.dancer = true;
        Some("Dancer")
    }
}

/// Registers the achievement resource and the survival tracker.
pub struct AchievementsPlugin;

impl Plugin for AchievementsPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<Achievements>()
            .add_systems(Update, check_survivor);
    }
}

/// "Survivor": keep the pet healthy for five continuous minutes.
///
/// Healthy band (hunger is inverted — **high hunger is bad**): `energy > 50`,
/// `happiness > 50`, `hunger < 50`. The streak resets whenever any stat leaves
/// the band.
pub fn check_survivor(
    time: Res<Time>,
    pet: Query<&Pet>,
    mut achievements: ResMut<Achievements>,
    mut notices: MessageWriter<Notice>,
) {
    if achievements.survivor {
        return;
    }
    let Ok(pet) = pet.single() else {
        return;
    };

    let healthy = pet.energy > SURVIVOR_THRESHOLD
        && pet.happiness > SURVIVOR_THRESHOLD
        && pet.hunger < SURVIVOR_THRESHOLD;

    if !healthy {
        achievements.survivor_time = 0.0;
        return;
    }

    achievements.survivor_time += time.delta_secs();
    if achievements.survivor_time >= SURVIVOR_SECONDS {
        achievements.survivor = true;
        notices.write(Notice::achievement("Survivor"));
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn set_without_dance() -> HashSet<AnimState> {
        [AnimState::Idle, AnimState::Happy, AnimState::TailWag]
            .into_iter()
            .collect()
    }

    fn set_with_dance() -> HashSet<AnimState> {
        [AnimState::Idle, AnimState::Happy, AnimState::Dance]
            .into_iter()
            .collect()
    }

    #[test]
    fn first_feed_unlocks_once() {
        let mut a = Achievements::default();
        assert_eq!(a.register_feed(), Some("First Feed"));
        assert_eq!(a.register_feed(), None, "idempotent");
    }

    #[test]
    fn pet_lover_unlocks_at_ten() {
        let mut a = Achievements::default();
        for _ in 0..(PET_LOVER_COUNT - 1) {
            assert_eq!(a.register_pet(), None);
        }
        assert_eq!(a.register_pet(), Some("Pet Lover"));
        assert_eq!(a.register_pet(), None, "only announced once");
    }

    #[test]
    fn dancer_without_dance_counts_any_action() {
        let mut a = Achievements::default();
        let available = set_without_dance();
        assert_eq!(a.register_action(AnimState::Happy, &available), None);
        assert_eq!(a.register_action(AnimState::TailWag, &available), None);
        assert_eq!(
            a.register_action(AnimState::Happy, &available),
            Some("Dancer")
        );
    }

    #[test]
    fn dancer_with_dance_counts_only_dance() {
        let mut a = Achievements::default();
        let available = set_with_dance();
        for _ in 0..5 {
            assert_eq!(
                a.register_action(AnimState::Happy, &available),
                None,
                "Happy must not count when Dance exists"
            );
        }
        for _ in 0..(DANCER_COUNT - 1) {
            assert_eq!(a.register_action(AnimState::Dance, &available), None);
        }
        assert_eq!(
            a.register_action(AnimState::Dance, &available),
            Some("Dancer")
        );
    }
}
