//! Transient on-screen notifications.
//!
//! Achievements and action feedback used to be `println!`-only, which is
//! invisible for a GUI app launched from Finder / Explorer. Toasts surface them
//! in the overlay itself: newest at the top, oldest evicted past
//! [`MAX_TOASTS`], each fading out over its last [`TOAST_FADE_SECS`].

use bevy::prelude::*;

use crate::command::{Notice, NoticeKind};
use crate::config::{MAX_TOASTS, TOAST_FADE_SECS, TOAST_SECS};
use crate::ui::theme::{self, ACCENT_GOLD, RADIUS_ROW, TEXT, TOAST_SURFACE};
use crate::ui::PetUiSystems;

/// Root container that stacks toasts at the top of the window.
#[derive(Component)]
struct ToastRoot;

/// A single toast with its lifetime.
#[derive(Component)]
struct Toast {
    timer: Timer,
}

/// Registers the toast surface.
pub struct ToastPlugin;

impl Plugin for ToastPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(PostStartup, spawn_toast_root).add_systems(
            Update,
            (receive_notices, tick_toasts)
                .chain()
                .in_set(PetUiSystems::Present),
        );
    }
}

fn spawn_toast_root(mut commands: Commands) {
    // Deliberately *not* a `UiBlocker`: toasts are non-interactive, so they must
    // never swallow clicks meant for the pet.
    commands.spawn((
        Node {
            position_type: PositionType::Absolute,
            top: Val::Px(4.0),
            left: Val::Px(4.0),
            right: Val::Px(4.0),
            flex_direction: FlexDirection::Column,
            align_items: AlignItems::Center,
            row_gap: Val::Px(2.0),
            ..default()
        },
        ToastRoot,
    ));
}

/// Alpha of a toast that has been alive for `elapsed` of `TOAST_SECS`.
///
/// Fully opaque until the fade window, then linear to zero.
pub fn toast_alpha(elapsed: f32) -> f32 {
    let fade_start = (TOAST_SECS - TOAST_FADE_SECS).max(0.0);
    if elapsed <= fade_start {
        1.0
    } else {
        ((TOAST_SECS - elapsed) / TOAST_FADE_SECS).clamp(0.0, 1.0)
    }
}

/// Text colour for a notice kind.
fn notice_color(kind: NoticeKind) -> Color {
    match kind {
        NoticeKind::Info => TEXT,
        NoticeKind::Achievement => ACCENT_GOLD,
    }
}

/// Spawn a toast for every incoming notice, evicting the oldest past the cap.
fn receive_notices(
    mut notices: MessageReader<Notice>,
    mut commands: Commands,
    root: Query<(Entity, Option<&Children>), With<ToastRoot>>,
) {
    let Ok((root_entity, children)) = root.single() else {
        return;
    };

    let mut live: Vec<Entity> = children
        .map(|children| children.iter().collect())
        .unwrap_or_default();

    for notice in notices.read() {
        // Mirror to stdout so `cargo run` / log capture keeps working.
        println!("[notice] {}", notice.text);

        while live.len() >= MAX_TOASTS {
            let oldest = live.remove(0);
            commands.entity(oldest).despawn();
        }

        let toast = commands
            .spawn((
                Text::new(notice.text.clone()),
                theme::font(theme::FONT_TOAST),
                TextColor(notice_color(notice.kind)),
                TextBackgroundColor(TOAST_SURFACE),
                Node {
                    padding: UiRect::axes(Val::Px(5.0), Val::Px(1.0)),
                    border_radius: BorderRadius::all(Val::Px(RADIUS_ROW)),
                    ..default()
                },
                Toast {
                    timer: Timer::from_seconds(TOAST_SECS, TimerMode::Once),
                },
            ))
            .id();
        commands.entity(root_entity).add_child(toast);
        live.push(toast);
    }
}

/// Age toasts: fade them out, then despawn.
fn tick_toasts(
    time: Res<Time>,
    mut commands: Commands,
    mut toasts: Query<(Entity, &mut Toast, &mut TextColor, &mut TextBackgroundColor)>,
) {
    for (entity, mut toast, mut color, mut background) in &mut toasts {
        toast.timer.tick(time.delta());
        if toast.timer.is_finished() {
            commands.entity(entity).despawn();
            continue;
        }
        let alpha = toast_alpha(toast.timer.elapsed_secs());
        color.0.set_alpha(alpha);
        background.0.set_alpha(TOAST_SURFACE.alpha() * alpha);
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn toast_is_opaque_before_the_fade_window() {
        assert_eq!(toast_alpha(0.0), 1.0);
        assert_eq!(toast_alpha(TOAST_SECS - TOAST_FADE_SECS), 1.0);
    }

    #[test]
    fn toast_fades_to_zero_at_the_end() {
        let mid = toast_alpha(TOAST_SECS - TOAST_FADE_SECS / 2.0);
        assert!(mid > 0.0 && mid < 1.0, "mid-fade must be partial: {mid}");
        assert_eq!(toast_alpha(TOAST_SECS), 0.0);
        assert_eq!(toast_alpha(TOAST_SECS + 5.0), 0.0);
    }

    #[test]
    fn notice_colors_distinguish_achievements() {
        assert_eq!(notice_color(NoticeKind::Info), TEXT);
        assert_eq!(notice_color(NoticeKind::Achievement), ACCENT_GOLD);
    }

    #[test]
    fn notice_text_is_ascii() {
        let notice = Notice::achievement("Pet Lover");
        assert!(notice.text.is_ascii());
        assert_eq!(notice.text, "Achievement: Pet Lover");
    }
}
