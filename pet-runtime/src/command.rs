//! User-intent message bus.
//!
//! Every user-facing surface (sprite clicks, the context menu, the optional
//! system tray and any future hotkey / IPC layer) expresses itself as a
//! [`PetCommand`] message instead of mutating the pet directly. A single
//! consumer — [`apply_commands`] — owns the effects, so:
//!
//! * the rules (how much a feed relieves hunger, which animation an action
//!   plays, what unlocks an achievement) live in exactly one place;
//! * new input surfaces need zero knowledge of vitals or the state machine;
//! * the effects are unit-testable as a pure function ([`resolve`]).
//!
//! Feedback flows the other way through [`Notice`], which the toast UI renders.

use bevy::prelude::*;

use crate::achievements::Achievements;
use crate::animation::{AnimState, AnimStateMachine, AnimationAssets};
use crate::config::{
    FEED_HUNGER_RELIEF, HAPPY_SECS, LOOP_ACTION_SECS, PET_HAPPINESS_GAIN, PLAY_HAPPINESS_GAIN,
    SLEEP_ENERGY_RESTORE, SLEEP_SECS,
};
use crate::pet::Pet;

/// System set holding [`apply_commands`]. Input surfaces run before it,
/// presentation runs after it.
#[derive(SystemSet, Debug, Clone, PartialEq, Eq, Hash)]
pub struct CommandSystems;

/// A deliberate user intent.
#[derive(Message, Debug, Clone, Copy, PartialEq, Eq)]
pub enum PetCommand {
    /// The sprite was clicked (stroked).
    Pet,
    /// Feed the pet.
    Feed,
    /// Play with the pet.
    Play,
    /// Put the pet to sleep for [`SLEEP_SECS`].
    Sleep,
    /// Play a specific animation the pet actually ships.
    PlayAnim(AnimState),
    /// Quit the application.
    Quit,
}

/// Severity / styling hint for a [`Notice`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NoticeKind {
    /// Routine feedback ("Fed  HGR -30").
    Info,
    /// Achievement unlocked.
    Achievement,
}

/// A short-lived, on-screen notification.
///
/// Text must stay ASCII — the embedded default font only covers
/// `U+0020..U+007E` (see `docs/standards/RUNTIME_UX.md`).
#[derive(Message, Debug, Clone)]
pub struct Notice {
    pub text: String,
    pub kind: NoticeKind,
}

impl Notice {
    /// Routine feedback notice.
    pub fn info(text: impl Into<String>) -> Self {
        Self {
            text: text.into(),
            kind: NoticeKind::Info,
        }
    }

    /// Achievement notice.
    pub fn achievement(name: &str) -> Self {
        Self {
            text: format!("Achievement: {name}"),
            kind: NoticeKind::Achievement,
        }
    }
}

/// The resolved effect of a [`PetCommand`], independent of the ECS.
///
/// Keeping resolution pure makes the command semantics unit-testable and keeps
/// [`apply_commands`] a thin adapter.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct CommandEffect {
    /// Animation to play as a one-shot action (state, optional duration).
    pub action: Option<(AnimState, Option<f32>)>,
    /// Happiness delta.
    pub happiness: f32,
    /// Energy delta.
    pub energy: f32,
    /// Hunger relief (positive = less hungry).
    pub hunger_relief: f32,
    /// Toast text, if this command reports itself.
    pub notice: Option<String>,
    /// Whether this counts as a deliberate action for achievements.
    pub deliberate: bool,
    /// Whether this is a feeding action (achievement bookkeeping).
    pub feeding: bool,
    /// Whether the app should exit.
    pub quit: bool,
}

/// Resolve a command into its effect, given the animations this pet ships.
pub fn resolve(command: PetCommand, assets: &AnimationAssets) -> CommandEffect {
    let happy = (
        AnimState::Happy,
        assets.action_duration(AnimState::Happy, HAPPY_SECS),
    );

    match command {
        PetCommand::Pet => CommandEffect {
            action: Some(happy),
            happiness: PET_HAPPINESS_GAIN,
            deliberate: true,
            ..Default::default()
        },
        PetCommand::Feed => CommandEffect {
            action: Some(happy),
            hunger_relief: FEED_HUNGER_RELIEF,
            notice: Some(format!("Fed   HGR -{}", FEED_HUNGER_RELIEF as i32)),
            deliberate: true,
            feeding: true,
            ..Default::default()
        },
        PetCommand::Play => CommandEffect {
            action: Some(happy),
            happiness: PLAY_HAPPINESS_GAIN,
            notice: Some(format!("Play  HAP +{}", PLAY_HAPPINESS_GAIN as i32)),
            deliberate: true,
            ..Default::default()
        },
        PetCommand::Sleep => CommandEffect {
            action: Some((AnimState::Sleep, Some(SLEEP_SECS))),
            energy: SLEEP_ENERGY_RESTORE,
            notice: Some(format!("Sleep NRG +{}", SLEEP_ENERGY_RESTORE as i32)),
            deliberate: true,
            ..Default::default()
        },
        PetCommand::PlayAnim(state) => CommandEffect {
            action: Some((state, assets.action_duration(state, LOOP_ACTION_SECS))),
            notice: Some(state.label().to_string()),
            deliberate: true,
            ..Default::default()
        },
        PetCommand::Quit => CommandEffect {
            quit: true,
            ..Default::default()
        },
    }
}

/// Registers the command bus and its single consumer.
pub struct CommandPlugin;

impl Plugin for CommandPlugin {
    fn build(&self, app: &mut App) {
        app.add_message::<PetCommand>()
            .add_message::<Notice>()
            .add_systems(Update, apply_commands.in_set(CommandSystems));
    }
}

/// Apply every queued [`PetCommand`]: mutate vitals, drive the state machine,
/// register achievements and emit user-visible notices.
pub fn apply_commands(
    mut commands: MessageReader<PetCommand>,
    mut sm: ResMut<AnimStateMachine>,
    mut pet_query: Query<&mut Pet>,
    mut achievements: ResMut<Achievements>,
    assets: Res<AnimationAssets>,
    mut notices: MessageWriter<Notice>,
    mut exit: MessageWriter<AppExit>,
) {
    for &command in commands.read() {
        let effect = resolve(command, &assets);

        if effect.quit {
            info!("Quit requested");
            exit.write(AppExit::Success);
            continue;
        }

        if let Ok(mut pet) = pet_query.single_mut() {
            if effect.happiness != 0.0 {
                pet.add_happiness(effect.happiness);
            }
            if effect.energy != 0.0 {
                pet.add_energy(effect.energy);
            }
            if effect.hunger_relief != 0.0 {
                pet.relieve_hunger(effect.hunger_relief);
            }
        }

        if let Some((state, duration)) = effect.action {
            sm.play_action(state, duration);
        }

        if effect.feeding {
            if let Some(name) = achievements.register_feed() {
                notices.write(Notice::achievement(name));
            }
        }
        if command == PetCommand::Pet {
            if let Some(name) = achievements.register_pet() {
                notices.write(Notice::achievement(name));
            }
        }
        if effect.deliberate {
            let state = effect.action.map(|(s, _)| s).unwrap_or(AnimState::Idle);
            if let Some(name) = achievements.register_action(state, &assets.available) {
                notices.write(Notice::achievement(name));
            }
        }

        if let Some(text) = effect.notice {
            notices.write(Notice::info(text));
        }
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::animation::SpriteAnimation;
    use std::collections::{HashMap, HashSet};

    fn assets() -> AnimationAssets {
        let mut animations: HashMap<AnimState, SpriteAnimation> = HashMap::new();
        for (state, loop_anim, duration) in [
            (AnimState::Idle, true, Some(3.0)),
            (AnimState::Happy, true, Some(1.5)),
            (AnimState::Dance, true, Some(3.0)),
            (AnimState::Wave, false, Some(2.0)),
        ] {
            animations.insert(
                state,
                SpriteAnimation {
                    frames: Vec::new(),
                    fps: 12.0,
                    loop_anim,
                    default_duration: duration,
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
    fn feed_relieves_hunger_and_reports() {
        let effect = resolve(PetCommand::Feed, &assets());
        assert_eq!(effect.hunger_relief, FEED_HUNGER_RELIEF);
        assert_eq!(effect.action, Some((AnimState::Happy, Some(1.5))));
        assert!(effect.feeding && effect.deliberate);
        assert!(effect.notice.is_some(), "feeding must be visible");
    }

    #[test]
    fn play_raises_happiness() {
        let effect = resolve(PetCommand::Play, &assets());
        assert_eq!(effect.happiness, PLAY_HAPPINESS_GAIN);
        assert!(!effect.feeding);
    }

    #[test]
    fn pet_is_silent_but_deliberate() {
        let effect = resolve(PetCommand::Pet, &assets());
        assert_eq!(effect.happiness, PET_HAPPINESS_GAIN);
        assert!(effect.deliberate);
        assert!(
            effect.notice.is_none(),
            "petting is frequent; it must not spam toasts"
        );
    }

    #[test]
    fn sleep_is_timed_and_restores_energy() {
        let effect = resolve(PetCommand::Sleep, &assets());
        assert_eq!(effect.action, Some((AnimState::Sleep, Some(SLEEP_SECS))));
        assert_eq!(effect.energy, SLEEP_ENERGY_RESTORE);
    }

    #[test]
    fn play_anim_uses_sheet_semantics() {
        let looping = resolve(PetCommand::PlayAnim(AnimState::Dance), &assets());
        assert_eq!(looping.action, Some((AnimState::Dance, Some(3.0))));

        let one_shot = resolve(PetCommand::PlayAnim(AnimState::Wave), &assets());
        assert_eq!(
            one_shot.action,
            Some((AnimState::Wave, None)),
            "non-looping sheets play to completion"
        );
    }

    #[test]
    fn quit_has_no_side_effects() {
        let effect = resolve(PetCommand::Quit, &assets());
        assert!(effect.quit);
        assert!(effect.action.is_none());
        assert_eq!(effect.happiness, 0.0);
    }
}
