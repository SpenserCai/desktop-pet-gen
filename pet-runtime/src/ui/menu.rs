//! The right-click action menu.
//!
//! Three properties make it correct where the previous fixed-position menu was
//! not:
//!
//! * **Data-driven rows** — care actions (Feed / Play) plus one row per
//!   animation the pet *actually ships* ([`AnimationAssets::available`] ∩
//!   [`ACTION_ORDER`]), so every animation is reachable on every body type and
//!   two different rows never map to the same animation by accident.
//! * **Cursor-anchored, clamped placement** — the panel pops up where the user
//!   right-clicked and is clamped inside the window, so no row can ever be
//!   clipped outside the overlay (the old menu overflowed a 256 px window and
//!   its last rows were both invisible and unclickable).
//! * **Visibility-based hiding** — the panel stays laid out while hidden
//!   (`Visibility::Hidden`), which keeps its measured size available for
//!   clamping and makes Bevy treat it as non-interactive.
//!
//! Rows emit [`PetCommand`]s; the menu itself never touches the pet.

use bevy::prelude::*;
use bevy::window::PrimaryWindow;

use crate::animation::{AnimState, AnimationAssets, ACTION_ORDER};
use crate::command::PetCommand;
use crate::config::{MAX_MENU_ITEMS, MENU_EDGE_PADDING, MENU_ITEM_HEIGHT, MENU_WIDTH, WINDOW_SIZE};
use crate::ui::icons::{spawn_icon, IconKind};
use crate::ui::theme::{
    self, ACCENT_DANGER, PAD, RADIUS_PANEL, RADIUS_ROW, ROW, ROW_GAP, ROW_HOVER, ROW_PRESSED,
    SURFACE, TEXT,
};
use crate::ui::{PetUiSystems, UiBlocker};

/// Whether the menu is shown, and where it was requested.
#[derive(Resource, Default)]
pub struct MenuState {
    /// Whether the panel is visible.
    pub visible: bool,
    /// Requested top-left position in **logical** window coordinates.
    pub anchor: Vec2,
}

/// Marker for the menu panel root, carrying its layout estimate.
#[derive(Component)]
pub struct MenuRoot {
    /// Fallback size used for clamping before the first layout pass.
    estimated_size: Vec2,
}

/// A menu row and the command it emits.
#[derive(Component)]
pub struct MenuItem(PetCommand);

/// One resolved row of the menu.
#[derive(Debug, Clone, PartialEq)]
pub struct MenuEntry {
    /// Command emitted when the row is pressed.
    pub command: PetCommand,
    /// Icon drawn on the left.
    pub icon: IconKind,
    /// ASCII label.
    pub label: &'static str,
}

/// Build the menu rows for the animations this pet ships.
///
/// Order: care actions, then available animations in [`ACTION_ORDER`], then
/// `Sleep` (only when the pet has a sleep animation), then `Quit`. The action
/// rows are capped so an exotic action set can never overflow the window.
pub fn menu_entries(assets: &AnimationAssets) -> Vec<MenuEntry> {
    let mut entries = vec![
        MenuEntry {
            command: PetCommand::Feed,
            icon: IconKind::Feed,
            label: "Feed",
        },
        MenuEntry {
            command: PetCommand::Play,
            icon: IconKind::Play,
            label: "Play",
        },
    ];

    // Reserve room for the trailing Sleep + Quit rows.
    let reserved = 1 + usize::from(assets.available.contains(&AnimState::Sleep));
    let budget = MAX_MENU_ITEMS.saturating_sub(entries.len() + reserved);

    for &state in ACTION_ORDER
        .iter()
        .filter(|state| assets.available.contains(state))
        .take(budget)
    {
        entries.push(MenuEntry {
            command: PetCommand::PlayAnim(state),
            icon: IconKind::for_state(state),
            label: state.label(),
        });
    }

    if assets.available.contains(&AnimState::Sleep) {
        entries.push(MenuEntry {
            command: PetCommand::Sleep,
            icon: IconKind::Sleep,
            label: "Sleep",
        });
    }
    entries.push(MenuEntry {
        command: PetCommand::Quit,
        icon: IconKind::Quit,
        label: "Quit",
    });

    entries
}

/// Estimated panel size for `rows` rows (logical px).
pub fn estimated_size(rows: usize) -> Vec2 {
    let height =
        rows as f32 * MENU_ITEM_HEIGHT + rows.saturating_sub(1) as f32 * ROW_GAP + PAD * 2.0;
    Vec2::new(MENU_WIDTH, height)
}

/// Clamp a requested menu position so the whole panel stays inside the window.
///
/// Degrades gracefully when the panel cannot fit at all (tiny window): it is
/// pinned to the origin instead of being pushed to a negative offset.
pub fn clamp_menu_position(anchor: Vec2, menu_size: Vec2, window_size: Vec2) -> Vec2 {
    let pad = Vec2::splat(MENU_EDGE_PADDING);
    let upper = (window_size - menu_size - pad).max(Vec2::ZERO);
    let lower = pad.min(upper);
    anchor.max(lower).min(upper)
}

/// Registers the menu resources and systems.
pub struct MenuPlugin;

impl Plugin for MenuPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<MenuState>()
            .add_systems(PostStartup, spawn_menu)
            .add_systems(
                Update,
                (place_menu, row_feedback, row_activation).in_set(PetUiSystems::Input),
            );
    }
}

/// Spawn the (initially hidden) menu panel.
fn spawn_menu(mut commands: Commands, assets: Res<AnimationAssets>) {
    let entries = menu_entries(&assets);
    let estimate = estimated_size(entries.len());
    info!(
        "Menu: {} rows, estimated size {:?}",
        entries.len(),
        estimate
    );

    commands
        .spawn((
            Node {
                position_type: PositionType::Absolute,
                left: Val::Px(MENU_EDGE_PADDING),
                top: Val::Px(MENU_EDGE_PADDING),
                width: Val::Px(MENU_WIDTH),
                flex_direction: FlexDirection::Column,
                padding: UiRect::all(Val::Px(PAD)),
                row_gap: Val::Px(ROW_GAP),
                border_radius: BorderRadius::all(Val::Px(RADIUS_PANEL)),
                ..default()
            },
            BackgroundColor(SURFACE),
            Visibility::Hidden,
            MenuRoot {
                estimated_size: estimate,
            },
            UiBlocker,
        ))
        .with_children(|panel| {
            for entry in entries {
                spawn_row(panel, &entry);
            }
        });
}

/// Spawn one menu row: icon + ASCII label, carrying its command.
fn spawn_row(parent: &mut ChildSpawnerCommands, entry: &MenuEntry) {
    let text_color = if entry.command == PetCommand::Quit {
        ACCENT_DANGER
    } else {
        TEXT
    };

    parent
        .spawn((
            Button,
            Node {
                width: Val::Percent(100.0),
                height: Val::Px(MENU_ITEM_HEIGHT),
                align_items: AlignItems::Center,
                column_gap: Val::Px(6.0),
                padding: UiRect::horizontal(Val::Px(4.0)),
                border_radius: BorderRadius::all(Val::Px(RADIUS_ROW)),
                ..default()
            },
            BackgroundColor(ROW),
            MenuItem(entry.command),
        ))
        .with_children(|row| {
            spawn_icon(row, entry.icon);
            row.spawn((
                Text::new(entry.label),
                theme::font(theme::FONT_MENU),
                TextColor(text_color),
            ));
        });
}

/// Query alias for the menu panel (keeps the system signature readable).
type PanelQuery<'w, 's> = Query<
    'w,
    's,
    (
        &'static mut Node,
        &'static mut Visibility,
        &'static ComputedNode,
        &'static MenuRoot,
    ),
>;

/// Position and show / hide the panel whenever [`MenuState`] changes.
fn place_menu(
    menu: Res<MenuState>,
    windows: Query<&Window, With<PrimaryWindow>>,
    mut panel: PanelQuery,
) {
    if !menu.is_changed() {
        return;
    }
    let window_size = windows
        .single()
        .map(|window| Vec2::new(window.width(), window.height()))
        .unwrap_or(Vec2::splat(WINDOW_SIZE));
    let scale = windows
        .single()
        .map(|window| window.scale_factor().max(0.1))
        .unwrap_or(1.0);

    for (mut node, mut visibility, computed, root) in &mut panel {
        // `ComputedNode::size` is physical; fall back to the estimate before the
        // first layout pass has measured the panel.
        let measured = computed.size / scale;
        let size = if measured.x > 1.0 && measured.y > 1.0 {
            measured
        } else {
            root.estimated_size
        };

        let position = clamp_menu_position(menu.anchor, size, window_size);
        node.left = Val::Px(position.x);
        node.top = Val::Px(position.y);
        *visibility = if menu.visible {
            Visibility::Inherited
        } else {
            Visibility::Hidden
        };
    }
}

/// Query alias for menu-row highlighting.
type RowFeedbackQuery<'w, 's> = Query<
    'w,
    's,
    (&'static Interaction, &'static mut BackgroundColor),
    (Changed<Interaction>, With<MenuItem>),
>;

/// Hover / press highlight for menu rows.
fn row_feedback(mut rows: RowFeedbackQuery) {
    for (interaction, mut background) in &mut rows {
        background.0 = match interaction {
            Interaction::Pressed => ROW_PRESSED,
            Interaction::Hovered => ROW_HOVER,
            Interaction::None => ROW,
        };
    }
}

/// Emit the row's command and dismiss the menu.
fn row_activation(
    rows: Query<(&Interaction, &MenuItem), Changed<Interaction>>,
    mut menu: ResMut<MenuState>,
    mut commands: MessageWriter<PetCommand>,
) {
    for (interaction, item) in &rows {
        if *interaction == Interaction::Pressed {
            commands.write(item.0);
            menu.visible = false;
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
    fn humanoid_menu_exposes_every_shipped_animation() {
        // Mirrors a full humanoid action set as produced by the generator.
        let assets = assets(&[
            AnimState::Idle,
            AnimState::Happy,
            AnimState::Sleepy,
            AnimState::Hungry,
            AnimState::Dance,
            AnimState::Sleep,
            AnimState::Wave,
            AnimState::Yawn,
            AnimState::Stretch,
            AnimState::LookAround,
        ]);
        let entries = menu_entries(&assets);
        let commands: Vec<PetCommand> = entries.iter().map(|entry| entry.command).collect();

        assert_eq!(
            commands,
            vec![
                PetCommand::Feed,
                PetCommand::Play,
                PetCommand::PlayAnim(AnimState::Dance),
                PetCommand::PlayAnim(AnimState::Wave),
                PetCommand::PlayAnim(AnimState::Yawn),
                PetCommand::PlayAnim(AnimState::Stretch),
                PetCommand::PlayAnim(AnimState::LookAround),
                PetCommand::Sleep,
                PetCommand::Quit,
            ]
        );
        assert!(entries.len() <= MAX_MENU_ITEMS);
    }

    #[test]
    fn quadruped_menu_has_no_humanoid_rows() {
        let assets = assets(&[AnimState::Idle, AnimState::TailWag, AnimState::Sit]);
        let entries = menu_entries(&assets);
        let commands: Vec<PetCommand> = entries.iter().map(|entry| entry.command).collect();

        assert_eq!(
            commands,
            vec![
                PetCommand::Feed,
                PetCommand::Play,
                PetCommand::PlayAnim(AnimState::TailWag),
                PetCommand::PlayAnim(AnimState::Sit),
                PetCommand::Quit,
            ]
        );
        assert!(
            !commands.contains(&PetCommand::Sleep),
            "no sleep sheet → no Sleep row"
        );
    }

    #[test]
    fn menu_is_capped_and_always_keeps_quit() {
        // Every action animation available: the cap must hold.
        let mut states = vec![AnimState::Idle, AnimState::Sleep];
        states.extend_from_slice(ACTION_ORDER);
        let entries = menu_entries(&assets(&states));

        assert!(entries.len() <= MAX_MENU_ITEMS, "menu must respect the cap");
        assert_eq!(
            entries.last().map(|entry| entry.command),
            Some(PetCommand::Quit)
        );
        assert!(entries
            .iter()
            .any(|entry| entry.command == PetCommand::Sleep));
    }

    #[test]
    fn menu_labels_are_ascii_only() {
        let mut states = vec![AnimState::Idle, AnimState::Sleep];
        states.extend_from_slice(ACTION_ORDER);
        for entry in menu_entries(&assets(&states)) {
            assert!(
                entry.label.is_ascii(),
                "label {:?} is not ASCII; the embedded font would render tofu",
                entry.label
            );
        }
    }

    #[test]
    fn estimated_size_grows_with_rows() {
        let small = estimated_size(3);
        let large = estimated_size(9);
        assert_eq!(small.x, MENU_WIDTH);
        assert!(large.y > small.y);
        assert!(
            estimated_size(MAX_MENU_ITEMS).y < WINDOW_SIZE,
            "a full menu must fit inside the window"
        );
    }

    #[test]
    fn placement_keeps_the_panel_inside_the_window() {
        let window = Vec2::splat(WINDOW_SIZE);
        let size = estimated_size(9);

        // Bottom-right corner request → clamped so the panel stays visible.
        let position = clamp_menu_position(Vec2::new(295.0, 295.0), size, window);
        assert!(position.x + size.x <= WINDOW_SIZE);
        assert!(position.y + size.y <= WINDOW_SIZE);

        // Top-left request → padded away from the edge.
        let position = clamp_menu_position(Vec2::ZERO, size, window);
        assert_eq!(position, Vec2::splat(MENU_EDGE_PADDING));

        // A request in the middle is honoured verbatim.
        let position = clamp_menu_position(Vec2::new(40.0, 30.0), size, window);
        assert_eq!(position, Vec2::new(40.0, 30.0));
    }

    #[test]
    fn placement_degrades_gracefully_for_oversized_panels() {
        let window = Vec2::splat(100.0);
        let position = clamp_menu_position(Vec2::new(80.0, 80.0), Vec2::splat(200.0), window);
        assert_eq!(position, Vec2::ZERO, "never clamp to a negative offset");
    }
}
