//! Bottom-left status HUD: vitals plus the currently rendered animation state.
//!
//! Showing the effective state makes the state machine observable during
//! testing ("did that click really play Wave?") without a debugger, and the
//! vitals are colour-coded with hunger inverted (**high hunger is bad**).
//!
//! The HUD only rewrites its text nodes when a *displayed* value changes, so it
//! stays real-time without re-laying-out the UI every frame.

use bevy::prelude::*;

use crate::animation::{AnimState, AnimStateMachine};
use crate::pet::Pet;
use crate::ui::theme::{
    self, good_stat_color, hunger_color, HUD_SURFACE, PAD, RADIUS_ROW, TEXT_DIM,
};
use crate::ui::{PetUiSystems, UiBlocker};

/// Which value a HUD text node displays.
#[derive(Component, Debug, Clone, Copy, PartialEq, Eq)]
pub enum StatusField {
    Energy,
    Happiness,
    Hunger,
    State,
}

/// Snapshot of everything the HUD displays, used for change detection.
#[derive(Resource, Default, PartialEq, Eq, Clone, Copy, Debug)]
pub struct HudSnapshot {
    energy: i32,
    happiness: i32,
    hunger: i32,
    state: Option<AnimState>,
}

/// Registers the HUD.
pub struct HudPlugin;

impl Plugin for HudPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<HudSnapshot>()
            .add_systems(PostStartup, spawn_hud)
            .add_systems(Update, update_hud.in_set(PetUiSystems::Present));
    }
}

fn spawn_hud(mut commands: Commands) {
    commands
        .spawn((
            Node {
                position_type: PositionType::Absolute,
                bottom: Val::Px(4.0),
                left: Val::Px(4.0),
                flex_direction: FlexDirection::Column,
                row_gap: Val::Px(1.0),
                padding: UiRect::axes(Val::Px(PAD), Val::Px(3.0)),
                border_radius: BorderRadius::all(Val::Px(RADIUS_ROW)),
                ..default()
            },
            BackgroundColor(HUD_SURFACE),
            UiBlocker,
        ))
        .with_children(|panel| {
            panel
                .spawn(Node {
                    flex_direction: FlexDirection::Row,
                    column_gap: Val::Px(7.0),
                    ..default()
                })
                .with_children(|row| {
                    for field in [
                        StatusField::Energy,
                        StatusField::Happiness,
                        StatusField::Hunger,
                    ] {
                        row.spawn((
                            Text::new(field.placeholder()),
                            theme::font(theme::FONT_HUD),
                            TextColor(TEXT_DIM),
                            field,
                        ));
                    }
                });
            panel.spawn((
                Text::new(StatusField::State.placeholder()),
                theme::font(theme::FONT_HUD),
                TextColor(TEXT_DIM),
                StatusField::State,
            ));
        });
}

impl StatusField {
    /// Placeholder text shown before the first update.
    fn placeholder(self) -> &'static str {
        match self {
            Self::Energy => "NRG --",
            Self::Happiness => "HAP --",
            Self::Hunger => "HGR --",
            Self::State => "ST  --",
        }
    }
}

/// Render `snapshot` into the HUD text for `field`.
///
/// Pure formatting helper so the display contract is unit-testable (and stays
/// ASCII-only for the embedded font).
pub fn field_text(field: StatusField, snapshot: HudSnapshot) -> String {
    match field {
        StatusField::Energy => format!("NRG {}", snapshot.energy),
        StatusField::Happiness => format!("HAP {}", snapshot.happiness),
        StatusField::Hunger => format!("HGR {}", snapshot.hunger),
        StatusField::State => format!(
            "ST  {}",
            snapshot.state.map(|state| state.label()).unwrap_or("--")
        ),
    }
}

/// Colour for `field` given the raw (unrounded) vitals.
fn field_color(field: StatusField, pet: &Pet) -> Color {
    match field {
        StatusField::Energy => good_stat_color(pet.energy),
        StatusField::Happiness => good_stat_color(pet.happiness),
        StatusField::Hunger => hunger_color(pet.hunger),
        StatusField::State => TEXT_DIM,
    }
}

fn update_hud(
    pet: Query<&Pet>,
    sm: Res<AnimStateMachine>,
    mut snapshot: ResMut<HudSnapshot>,
    mut fields: Query<(&mut Text, &mut TextColor, &StatusField)>,
) {
    let Ok(pet) = pet.single() else {
        return;
    };

    let current = HudSnapshot {
        energy: pet.energy.round() as i32,
        happiness: pet.happiness.round() as i32,
        hunger: pet.hunger.round() as i32,
        state: Some(sm.effective()),
    };
    if *snapshot == current {
        return;
    }
    *snapshot = current;

    for (mut text, mut color, field) in &mut fields {
        *text = Text::new(field_text(*field, current));
        *color = TextColor(field_color(*field, pet));
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn snapshot() -> HudSnapshot {
        HudSnapshot {
            energy: 80,
            happiness: 70,
            hunger: 20,
            state: Some(AnimState::Dance),
        }
    }

    #[test]
    fn field_text_is_ascii_and_labelled() {
        for field in [
            StatusField::Energy,
            StatusField::Happiness,
            StatusField::Hunger,
            StatusField::State,
        ] {
            let text = field_text(field, snapshot());
            assert!(text.is_ascii(), "{text:?} must be ASCII");
        }
        assert_eq!(field_text(StatusField::Energy, snapshot()), "NRG 80");
        assert_eq!(field_text(StatusField::Hunger, snapshot()), "HGR 20");
        assert_eq!(field_text(StatusField::State, snapshot()), "ST  Dance");
    }

    #[test]
    fn state_field_falls_back_before_the_first_frame() {
        let empty = HudSnapshot::default();
        assert_eq!(field_text(StatusField::State, empty), "ST  --");
    }

    #[test]
    fn snapshot_equality_drives_change_detection() {
        assert_eq!(snapshot(), snapshot());
        let mut other = snapshot();
        other.state = Some(AnimState::Idle);
        assert_ne!(snapshot(), other, "a state change must refresh the HUD");
    }
}
