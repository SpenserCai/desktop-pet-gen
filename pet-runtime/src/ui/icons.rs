//! Font-free iconography.
//!
//! The embedded default font only covers ASCII (see [`super::theme`]), so icons
//! are **composed from primitive UI nodes** — coloured rectangles, circles and
//! rotated bars ([`UiTransform`] supports rotation) — inside a fixed
//! [`ICON_SIZE`]² box. That keeps the binary self-contained (no font or image
//! assets, no license obligations), renders identically on every platform, and
//! stays trivially extensible: add an [`IconKind`] variant plus its shape list.

use bevy::prelude::*;

use crate::animation::AnimState;
use crate::ui::theme::{ICON_SIZE, ROW};

/// A primitive shape inside the icon box, positioned from the top-left corner.
#[derive(Debug, Clone, Copy)]
struct Shape {
    /// Width in logical px.
    w: f32,
    /// Height in logical px.
    h: f32,
    /// Offset from the icon box's left edge.
    x: f32,
    /// Offset from the icon box's top edge.
    y: f32,
    /// Corner radius (use `w / 2` for a circle).
    radius: f32,
    /// Clockwise rotation in degrees, about the shape's centre.
    rotation: f32,
}

impl Shape {
    const fn new(w: f32, h: f32, x: f32, y: f32, radius: f32) -> Self {
        Self {
            w,
            h,
            x,
            y,
            radius,
            rotation: 0.0,
        }
    }

    const fn rotated(mut self, degrees: f32) -> Self {
        self.rotation = degrees;
        self
    }
}

/// Semantic icon identity. Each maps to an accent colour and a shape list.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum IconKind {
    /// Food in a dish.
    Feed,
    /// A ball.
    Play,
    /// Two dancing legs.
    Dance,
    /// A raised, waving arm.
    Wave,
    /// A "Z" for sleeping.
    Sleep,
    /// Two eyes looking around.
    Look,
    /// An open mouth (yawn).
    Yawn,
    /// A vertical stretch.
    Stretch,
    /// Neutral marker for any other animation.
    Generic,
    /// A cross (quit).
    Quit,
}

/// Shape tables. Declared as named constants so they live in static memory
/// (an inline `&[Shape::new(..)]` inside a `match` arm is a temporary — const
/// promotion does not apply to `const fn` calls).
mod shapes {
    use super::Shape;

    pub const FEED: &[Shape] = &[
        Shape::new(4.0, 4.0, 4.0, 1.0, 2.0),
        Shape::new(10.0, 5.0, 1.0, 6.0, 2.5),
    ];
    pub const PLAY: &[Shape] = &[Shape::new(10.0, 10.0, 1.0, 1.0, 5.0)];
    pub const DANCE: &[Shape] = &[
        Shape::new(2.0, 11.0, 2.5, 0.5, 1.0).rotated(20.0),
        Shape::new(2.0, 11.0, 7.5, 0.5, 1.0).rotated(-20.0),
    ];
    pub const WAVE: &[Shape] = &[
        Shape::new(4.0, 4.0, 6.5, 0.5, 2.0),
        Shape::new(2.0, 8.0, 4.0, 4.0, 1.0).rotated(-18.0),
    ];
    pub const SLEEP: &[Shape] = &[
        Shape::new(8.0, 2.0, 2.0, 1.5, 1.0),
        Shape::new(2.0, 8.0, 5.0, 2.0, 1.0).rotated(45.0),
        Shape::new(8.0, 2.0, 2.0, 8.5, 1.0),
    ];
    pub const LOOK: &[Shape] = &[
        Shape::new(3.5, 3.5, 1.0, 4.0, 1.75),
        Shape::new(3.5, 3.5, 7.5, 4.0, 1.75),
    ];
    pub const YAWN: &[Shape] = &[Shape::new(6.0, 9.0, 3.0, 1.5, 3.0)];
    pub const STRETCH: &[Shape] = &[
        Shape::new(7.0, 2.0, 2.5, 0.5, 1.0),
        Shape::new(2.0, 8.0, 5.0, 2.0, 1.0),
        Shape::new(7.0, 2.0, 2.5, 9.5, 1.0),
    ];
    pub const GENERIC: &[Shape] = &[Shape::new(6.0, 6.0, 3.0, 3.0, 3.0)];
    pub const QUIT: &[Shape] = &[
        Shape::new(2.0, 12.0, 5.0, 0.0, 1.0).rotated(45.0),
        Shape::new(2.0, 12.0, 5.0, 0.0, 1.0).rotated(-45.0),
    ];
}

impl IconKind {
    /// Pick the most descriptive icon for an animation state.
    pub fn for_state(state: AnimState) -> Self {
        match state {
            AnimState::Dance | AnimState::Spin | AnimState::Wobble | AnimState::Shake => {
                Self::Dance
            }
            AnimState::Wave | AnimState::Scratch | AnimState::Pounce => Self::Wave,
            AnimState::Sleep | AnimState::Sleepy => Self::Sleep,
            AnimState::LookAround | AnimState::TiltHead | AnimState::Tilt => Self::Look,
            AnimState::Yawn => Self::Yawn,
            AnimState::Stretch | AnimState::StretchVertical | AnimState::Float => Self::Stretch,
            AnimState::Happy | AnimState::Bounce | AnimState::BounceSmall => Self::Play,
            AnimState::Hungry => Self::Feed,
            _ => Self::Generic,
        }
    }

    /// Accent colour of this icon.
    pub fn accent(self) -> Color {
        match self {
            Self::Feed => Color::srgb(1.0, 0.72, 0.36),
            Self::Play => Color::srgb(0.55, 0.86, 0.52),
            Self::Dance => Color::srgb(0.78, 0.58, 1.0),
            Self::Wave => Color::srgb(0.45, 0.82, 0.95),
            Self::Sleep => Color::srgb(0.60, 0.66, 0.95),
            Self::Look => Color::srgb(0.42, 0.88, 0.80),
            Self::Yawn => Color::srgb(0.68, 0.76, 1.0),
            Self::Stretch => Color::srgb(0.85, 0.90, 0.45),
            Self::Generic => Color::srgb(0.72, 0.76, 0.86),
            Self::Quit => Color::srgb(0.95, 0.45, 0.45),
        }
    }

    /// Primitive shapes composing this icon inside a [`ICON_SIZE`]² box.
    fn shapes(self) -> &'static [Shape] {
        match self {
            Self::Feed => shapes::FEED,
            Self::Play => shapes::PLAY,
            Self::Dance => shapes::DANCE,
            Self::Wave => shapes::WAVE,
            Self::Sleep => shapes::SLEEP,
            Self::Look => shapes::LOOK,
            Self::Yawn => shapes::YAWN,
            Self::Stretch => shapes::STRETCH,
            Self::Generic => shapes::GENERIC,
            Self::Quit => shapes::QUIT,
        }
    }
}

/// Bundle for a single primitive shape.
fn shape_bundle(shape: Shape, color: Color) -> impl Bundle {
    (
        Node {
            position_type: PositionType::Absolute,
            left: Val::Px(shape.x),
            top: Val::Px(shape.y),
            width: Val::Px(shape.w),
            height: Val::Px(shape.h),
            border_radius: BorderRadius::all(Val::Px(shape.radius)),
            ..default()
        },
        BackgroundColor(color),
        UiTransform::from_rotation(Rot2::degrees(shape.rotation)),
    )
}

/// Spawn an icon box as a child of `parent`.
pub fn spawn_icon(parent: &mut ChildSpawnerCommands, kind: IconKind) {
    let accent = kind.accent();
    parent
        .spawn((
            Node {
                width: Val::Px(ICON_SIZE),
                height: Val::Px(ICON_SIZE),
                flex_shrink: 0.0,
                ..default()
            },
            // Transparent container: only the shapes are visible.
            BackgroundColor(ROW),
        ))
        .with_children(|icon| {
            for shape in kind.shapes() {
                icon.spawn(shape_bundle(*shape, accent));
            }
        });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    const ALL: &[IconKind] = &[
        IconKind::Feed,
        IconKind::Play,
        IconKind::Dance,
        IconKind::Wave,
        IconKind::Sleep,
        IconKind::Look,
        IconKind::Yawn,
        IconKind::Stretch,
        IconKind::Generic,
        IconKind::Quit,
    ];

    #[test]
    fn every_icon_has_shapes_inside_its_box() {
        for kind in ALL {
            let shapes = kind.shapes();
            assert!(!shapes.is_empty(), "{kind:?} has no shapes");
            for shape in shapes {
                assert!(
                    shape.x >= 0.0 && shape.y >= 0.0,
                    "{kind:?} shape starts outside the box"
                );
                assert!(
                    shape.x + shape.w <= ICON_SIZE + f32::EPSILON,
                    "{kind:?} shape overflows horizontally"
                );
                assert!(
                    shape.y + shape.h <= ICON_SIZE + f32::EPSILON,
                    "{kind:?} shape overflows vertically"
                );
            }
        }
    }

    #[test]
    fn state_icons_are_meaningful() {
        assert_eq!(IconKind::for_state(AnimState::Dance), IconKind::Dance);
        assert_eq!(IconKind::for_state(AnimState::Wave), IconKind::Wave);
        assert_eq!(IconKind::for_state(AnimState::Sleep), IconKind::Sleep);
        assert_eq!(IconKind::for_state(AnimState::LookAround), IconKind::Look);
        assert_eq!(IconKind::for_state(AnimState::Yawn), IconKind::Yawn);
        assert_eq!(IconKind::for_state(AnimState::Stretch), IconKind::Stretch);
        // Unknown / exotic states must still get a drawable icon.
        assert_eq!(IconKind::for_state(AnimState::Sparkle), IconKind::Generic);
    }
}
