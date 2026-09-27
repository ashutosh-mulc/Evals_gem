"""
QuestionType — single source of truth for parsing question_type strings.

The question_type format is: <connectivity>_<group>_<feature>_<action>

Examples:
    "online_samsung_notes_create"        → connectivity=online, group=samsung,
                                           feature=notes, action=create,
                                           app_key=samsungnote
    "online_samsung_clock_timer_create"  → connectivity=online, group=samsung,
                                           feature=clock_timer (compound), action=create,
                                           app_key=clocktimer
    "online_device_volume_up"            → connectivity=online, group=device,
                                           feature=volume, action=up,
                                           app_key=device

Compound features (e.g. clock_timer, clock_alarm, clock_stopwatch) are detected
automatically: when len(parts) >= 5 and parts[2]_parts[3] exists in APP_CONFIGS
or APP_KEY_MAP, the feature is the compound and the action is parts[4].

Every consumer should read these fields instead of splitting the string itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class QuestionType:
    """Parsed question_type with all components resolved.

    Attributes:
        raw:          The original question_type string.
        connectivity: online | offline | disconnected
        group:        samsung | google | device | thirdparty
        feature:      notes | clock_timer | volume ...  (compound resolved)
        action:       create | up | play | launch ...
        app_key:      Canonical app key (e.g. samsungnote, clocktimer) or None.
    """

    raw: str
    connectivity: str
    group: str
    feature: str
    action: str
    app_key: Optional[str]

    # ── Convenience properties ──────────────────────────────────────

    @property
    def is_device_query(self) -> bool:
        """True if this is a device-level query (volume, battery, time, etc.)."""
        return self.group == "device"

    @property
    def is_compound_feature(self) -> bool:
        """True if the feature was resolved as a compound (e.g. clock_timer)."""
        return "_" in self.feature

    @property
    def is_visual(self) -> bool:
        """True if this is a visual query (action contains 'visual')."""
        return "visual" in self.action

    @property
    def action_with_suffix(self) -> str:
        """Everything after the feature: "thread_read" for online_samsung_message_thread_read.

        Equals ``action`` for the normal 4-part format.
        """
        n_prefix = 2 + len(self.feature.split("_")) if self.feature else 0
        return "_".join(self.raw.lower().split("_")[n_prefix:]) if n_prefix else ""

    # ── Parser ──────────────────────────────────────────────────────

    @classmethod
    def parse(cls, raw: str) -> "QuestionType":
        """Parse a question_type string into a QuestionType.

        Handles:
        - 4-part format: <connectivity>_<group>_<feature>_<action>
        - 5-part compound: <connectivity>_<group>_<feature_part1>_<feature_part2>_<action>
          (e.g. online_samsung_clock_timer_create → feature=clock_timer, action=create)

        Args:
            raw: The question_type string (e.g. "online_samsung_notes_create").

        Returns:
            QuestionType with all fields resolved. If the string is too short
            or unparseable, returns a QuestionType with empty/None fields.
        """
        from apps import APP_CONFIGS, APP_KEY_MAP

        parts = (raw or "").lower().split("_")
        if len(parts) < 4:
            return cls(
                raw=raw or "",
                connectivity=parts[0] if parts else "",
                group="",
                feature="",
                action="",
                app_key=None,
            )

        connectivity = parts[0]
        group = parts[1]
        feature = parts[2]
        action = parts[3]

        # Check for compound feature (clock_timer, clock_alarm, clock_stopwatch)
        # when there are 5+ parts: parts[2]_parts[3] might be a compound feature,
        # making the action parts[4].
        if len(parts) >= 5:
            compound = f"{parts[2]}_{parts[3]}"
            group_config = APP_CONFIGS.get(group, {})
            if compound in group_config or (group, compound) in APP_KEY_MAP:
                feature = compound
                action = parts[4]

        # Resolve app_key from (group, feature)
        app_key = APP_KEY_MAP.get((group, feature))

        return cls(
            raw=raw or "",
            connectivity=connectivity,
            group=group,
            feature=feature,
            action=action,
            app_key=app_key,
        )
