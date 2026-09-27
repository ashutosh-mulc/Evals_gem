"""
UITreeVisualizer: Visualizes the Android UI tree by overlaying bounding boxes on
screenshots and printing text-based tree hierarchies.

Two visualization modes:
1. Screenshot Overlay: Draws bounding boxes around UI nodes on the screenshot image,
   color-coded by node type, with labels for text/content-desc/resource-id.
2. Text Tree: Prints the UI node hierarchy as an indented tree with key attributes.

Usage:
    # Overlay UI tree nodes on a screenshot
    python ui_tree_visualizer.py --screenshot <path> --xml <path_to_xml> --output <output_path>

    # Print text-based tree hierarchy from XML
    python ui_tree_visualizer.py --xml <path_to_xml> --text-tree

    # Overlay with target day highlighting
    python ui_tree_visualizer.py --screenshot <path> --xml <path_to_xml> --target-day 23 --output <output_path>

    # Print text tree with calendar filter
    python ui_tree_visualizer.py --xml <path_to_xml> --text-tree --filter calendar
"""

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from typing import Optional, Dict, List, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class UITreeVisualizer:
    """Visualizes Android UI tree nodes on screenshots and as text tree hierarchies."""

    # Color scheme for different node types (R, G, B)
    COLOR_CALENDAR_NODE = (0, 180, 0)       # Green - calendar date nodes
    COLOR_CLICKABLE = (0, 100, 255)          # Blue - clickable nodes
    COLOR_TARGET_DAY = (255, 0, 0)            # Red - target day node
    COLOR_CURRENT_DATE = (255, 165, 0)        # Orange - current/selected date
    COLOR_DEFAULT = (128, 128, 128)           # Gray - all other nodes
    COLOR_TEXT_BG = (0, 0, 0)                 # Black - label background
    COLOR_TEXT = (255, 255, 255)              # White - label text

    # Line widths
    LINE_WIDTH_DEFAULT = 1
    LINE_WIDTH_CLICKABLE = 2
    LINE_WIDTH_CALENDAR = 2
    LINE_WIDTH_TARGET = 4
    LINE_WIDTH_CURRENT = 3

    def __init__(self, ui_tree_parser: Optional[UITreeParser] = None):
        """
        Args:
            ui_tree_parser: An existing UITreeParser instance. If None, creates one
                           when needed (requires device_id).
        """
        self.ui_tree_parser = ui_tree_parser

    def visualize_screenshot(
        self,
        screenshot_path: str,
        xml_path: str,
        output_path: str,
        target_day: Optional[int] = None,
        current_date: Optional[Dict] = None,
        show_labels: bool = True,
        min_node_size: int = 5,
        max_labels: int = 50,
    ) -> str:
        """
        Draw bounding boxes around UI tree nodes on the screenshot.

        Args:
            screenshot_path: Path to the original screenshot image.
            xml_path: Path to the UI tree XML dump.
            output_path: Path to save the annotated screenshot.
            target_day: If specified, highlights the node matching this day number.
            current_date: Dict with current date info (day, month, year) for highlighting.
            show_labels: Whether to show text labels on nodes.
            min_node_size: Minimum node dimension (width or height) to draw.
            max_labels: Maximum number of labels to draw (to avoid clutter).

        Returns:
            Path to the saved annotated screenshot.
        """
        if not HAS_PIL:
            print("[Visualizer] PIL/Pillow is required for screenshot visualization. Install with: pip install Pillow")
            return ""

        if not os.path.exists(screenshot_path):
            print(f"[Visualizer] Screenshot not found: {screenshot_path}")
            return ""

        if not os.path.exists(xml_path):
            print(f"[Visualizer] XML not found: {xml_path}")
            return ""

        # Parse UI tree
        nodes = self.ui_tree_parser.parse_ui_tree(xml_path) if self.ui_tree_parser else []
        if not nodes:
            # Try parsing directly
            nodes = self._parse_xml_nodes(xml_path)

        if not nodes:
            print("[Visualizer] No nodes found in UI tree XML.")
            return ""

        print(f"[Visualizer] Found {len(nodes)} nodes in UI tree.")

        # Load screenshot
        img = Image.open(screenshot_path)
        draw = ImageDraw.Draw(img)

        # Try to load a font
        font = self._load_font(img.width)

        # Find target day node if specified
        target_node = None
        if target_day is not None and current_date:
            target_node = self._find_target_day_node(nodes, target_day, current_date)

        # Find current date node
        current_node = None
        if current_date:
            current_node = self._find_current_date_node(nodes, current_date)

        # Draw nodes
        labels_drawn = 0
        for node in nodes:
            bounds_str = node.get("bounds", "")
            x1, y1, x2, y2 = self._parse_bounds(bounds_str)
            if x1 is None:
                continue

            width = x2 - x1
            height = y2 - y1
            if width < min_node_size or height < min_node_size:
                continue

            # Determine node type and color
            is_target = (node is target_node) or (target_node and node.get("bounds") == target_node.get("bounds"))
            is_current = (node is current_node) or (current_node and node.get("bounds") == current_node.get("bounds"))
            is_calendar = self._is_calendar_node(node)
            is_clickable = node.get("clickable", "false") == "true"

            if is_target:
                color = self.COLOR_TARGET_DAY
                line_width = self.LINE_WIDTH_TARGET
            elif is_current:
                color = self.COLOR_CURRENT_DATE
                line_width = self.LINE_WIDTH_CURRENT
            elif is_calendar:
                color = self.COLOR_CALENDAR_NODE
                line_width = self.LINE_WIDTH_CALENDAR
            elif is_clickable:
                color = self.COLOR_CLICKABLE
                line_width = self.LINE_WIDTH_CLICKABLE
            else:
                color = self.COLOR_DEFAULT
                line_width = self.LINE_WIDTH_DEFAULT

            # Draw bounding box
            draw.rectangle([x1, y1, x2, y2], outline=color, width=line_width)

            # Draw label
            if show_labels and labels_drawn < max_labels:
                label = self._make_label(node, is_target, is_current, is_calendar)
                if label:
                    self._draw_label(draw, label, x1, y1, font, color)
                    labels_drawn += 1

        # Draw legend
        self._draw_legend(draw, img.width, font)

        # Save
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        img.save(output_path)
        print(f"[Visualizer] Annotated screenshot saved to: {output_path}")

        return output_path

    def print_text_tree(
        self,
        xml_path: str,
        filter_type: Optional[str] = None,
        max_depth: int = 20,
        show_bounds: bool = True,
        show_resource_id: bool = True,
    ) -> None:
        """
        Print the UI tree as an indented text hierarchy.

        Args:
            xml_path: Path to the UI tree XML dump.
            filter_type: Optional filter - "calendar" to show only calendar-related nodes,
                        "clickable" for clickable nodes, None for all.
            max_depth: Maximum depth to print.
            show_bounds: Whether to show bounds in the output.
            show_resource_id: Whether to show resource-id in the output.
        """
        if not os.path.exists(xml_path):
            print(f"[Visualizer] XML not found: {xml_path}")
            return

        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
        except ET.ParseError as e:
            print(f"[Visualizer] Failed to parse XML: {e}")
            return

        print(f"\n{'='*80}")
        print(f"  UI Tree Hierarchy: {os.path.basename(xml_path)}")
        if filter_type:
            print(f"  Filter: {filter_type}")
        print(f"{'='*80}\n")

        self._print_tree_node(root, depth=0, max_depth=max_depth, filter_type=filter_type,
                              show_bounds=show_bounds, show_resource_id=show_resource_id)

        print(f"\n{'='*80}")

    def _print_tree_node(
        self,
        elem: ET.Element,
        depth: int,
        max_depth: int,
        filter_type: Optional[str],
        show_bounds: bool,
        show_resource_id: bool,
    ) -> bool:
        """
        Recursively print a tree node and its children.

        Returns:
            True if this node or any child was printed.
        """
        if depth > max_depth:
            return False

        # Get node attributes
        text = elem.get("text", "").strip()
        content_desc = elem.get("content-desc", "").strip()
        resource_id = elem.get("resource-id", "").strip()
        bounds = elem.get("bounds", "").strip()
        clickable = elem.get("clickable", "false")
        class_name = elem.get("class", "").strip()
        package = elem.get("package", "").strip()

        # Check if this node matches the filter
        node_dict = {
            "text": text,
            "content_desc": content_desc,
            "resource_id": resource_id,
            "bounds": bounds,
            "clickable": clickable,
            "class_name": class_name,
        }

        matches_filter = True
        if filter_type == "calendar":
            matches_filter = self._is_calendar_node(node_dict) or text or content_desc
        elif filter_type == "clickable":
            matches_filter = clickable == "true"

        # Print children first to determine if any match
        child_printed = False
        for child in elem:
            if self._print_tree_node(child, depth + 1, max_depth, filter_type,
                                     show_bounds, show_resource_id):
                child_printed = True

        # Print this node if it matches or has matching children
        if matches_filter or child_printed:
            indent = "  " * depth
            class_short = class_name.split(".")[-1] if class_name else "?"
            parts = [f"{indent}<{class_short}"]

            if text:
                parts.append(f' text="{text}"')
            if content_desc:
                parts.append(f' content-desc="{content_desc}"')
            if show_resource_id and resource_id:
                # Shorten resource-id
                rid_short = resource_id.split("/")[-1] if "/" in resource_id else resource_id
                parts.append(f' id="{rid_short}"')
            if show_bounds and bounds:
                parts.append(f' bounds={bounds}')
            if clickable == "true":
                parts.append(" [clickable]")

            # Mark calendar nodes
            if self._is_calendar_node(node_dict):
                parts.append(" ��")

            parts.append(">")
            print("".join(parts))
            return True

        return False

    @staticmethod
    def _parse_bounds(bounds_str: str) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
        """Parse bounds string '[x1,y1][x2,y2]' and return coordinates."""
        match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds_str)
        if match:
            return int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
        return None, None, None, None

    def _parse_xml_nodes(self, xml_path: str) -> List[Dict]:
        """Parse XML directly into node dicts (fallback when UITreeParser not available)."""
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
        except ET.ParseError:
            return []

        nodes = []
        for elem in root.iter():
            bounds_str = elem.get("bounds", "")
            x1, y1, x2, y2 = self._parse_bounds(bounds_str)
            if x1 is None:
                continue

            center_x = (x1 + x2) // 2
            center_y = (y1 + y2) // 2

            nodes.append({
                "text": elem.get("text", ""),
                "content_desc": elem.get("content-desc", ""),
                "resource_id": elem.get("resource-id", ""),
                "bounds": bounds_str,
                "clickable": elem.get("clickable", "false"),
                "enabled": elem.get("enabled", "true"),
                "class_name": elem.get("class", ""),
                "package": elem.get("package", ""),
                "selected": elem.get("selected", "false"),
                "focused": elem.get("focused", "false"),
                "center_x": center_x,
                "center_y": center_y,
            })

        return nodes

    def _find_target_day_node(self, nodes: List[Dict], target_day: int, current_date: Dict) -> Optional[Dict]:
        """Find the UI node corresponding to the target day."""
        month_name = ["", "January", "February", "March", "April", "May", "June",
                       "July", "August", "September", "October", "November", "December"]
        month = current_date.get("month", 1)
        ye

    @staticmethod
    def _make_label(node: Dict, is_target: bool, is_current: bool, is_calendar: bool) -> str:
        """Create a short label for a node."""
        text = node.get("text", "").strip()
        content_desc = node.get("content_desc", "").strip()
        resource_id = node.get("resource_id", "").strip()

        parts = []
        if is_target:
            parts.append("��")
        elif is_current:
            parts.append("��")
        elif is_calendar:
            parts.append("��")

        if text:
            parts.append(f'"{text}"')
        elif content_desc:
            # Truncate long content-desc
            cd_short = content_desc[:30] + "..." if len(content_desc) > 30 else content_desc
            parts.append(f'[{cd_short}]')

        if resource_id:
            rid_short = resource_id.split("/")[-1] if "/" in resource_id else resource_id
            if rid_short:
                parts.append(f"id:{rid_short}")

        return " ".join(parts)

    def _draw_label(
        self,
        draw: ImageDraw.Draw,
        label: str,
        x: int,
        y: int,
        font,
        color: tuple,
    ) -> None:
        """Draw a text label with background at the given position."""
        if not label:
            return

        # Calculate text size
        try:
            bbox = draw.textbbox((0, 0), label, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
        except Exception:
            text_w = len(label) * 6
            text_h = 12

        padding = 2
        bg_x1 = x
        bg_y1 = max(0, y - text_h - 2 * padding)
        bg_x2 = x + text_w + 2 * padding
        bg_y2 = y

        # Draw background
        draw.rectangle([bg_x1, bg_y1, bg_x2, bg_y2], fill=self.COLOR_TEXT_BG)

        # Draw text
        draw.text((bg_x1 + padding, bg_y1 + padding), label, fill=color, font=font)

    def _draw_legend(self, draw: ImageDraw.Draw, img_width: int, font) -> None:
        """Draw a color legend in the top-right corner."""
        legend_items = [
            ("Target Day", self.COLOR_TARGET_DAY),
            ("Current Date", self.COLOR_CURRENT_DATE),
            ("Calendar Node", self.COLOR_CALENDAR_NODE),
            ("Clickable", self.COLOR_CLICKABLE),
            ("Other", self.COLOR_DEFAULT),
        ]

        x = img_width - 180
        y = 10
        line_height = 20

        # Background
        total_h = len(legend_items) * line_height + 10
        draw.rectangle([x - 10, y - 5, img_width - 5, y + total_h], fill=(0, 0, 0, 180))

        for label, color in legend_items:
            draw.rectangle([x, y, x + 15, y + 12], outline=color, width=2)
            draw.text((x + 20, y - 2), label, fill=(255, 255, 255), font=font)
            y += line_height

    @staticmethod
    def _load_font(img_width: int):
        """Try to load a suitable font, falling back to default."""
        font_size = max(10, min(16, img_width // 80))

        # Try common font paths
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "C:\\Windows\\Fonts\\arial.ttf",
        ]

        for path in font_paths:
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, font_size)
                except Exception:
                    continue

        try:
            return ImageFont.load_default()
        except Exception:
            return None


def main():
    parser = argparse.ArgumentParser(
        description="Visualize Android UI Tree: Overlay on screenshot or print text hierarchy."
    )
    parser.add_argument(
        "--screenshot",
        type=str,
        default=None,
        help="Path to the screenshot image for overlay visualization",
    )
    parser.add_argument(
        "--xml",
        type=str,
        required=True,
        help="Path to the UI tree XML dump",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output path for annotated screenshot (default: <xml_dir>/visualized_<screenshot_name>.png)",
    )
    parser.add_argument(
        "--text-tree",
        action="store_true",
        help="Print text-based tree hierarchy",
    )
    parser.add_argument(
        "--filter",
        type=str,
        choices=["calendar", "clickable"],
        default=None,
        help="Filter nodes shown in text tree",
    )
    parser.add_argument(
        "--target-day",
        type=int,
        default=None,
        help="Target day number to highlight in visualization",
    )
    parser.add_argument(
        "--screenshot-month",
        type=int,
        default=None,
        help="Month shown in screenshot (for target day search)",
    )
    parser.add_argument(
        "--screenshot-year",
        type=int,
        default=None,
        help="Year shown in screenshot (for target day search)",
    )
    parser.add_argument(
        "--no-labels",
        action="store_true",
        help="Don't draw text labels on overlay",
    )
    parser.add_argument(
        "--max-labels",
        type=int,
        default=50,
        help="Maximum number of labels to draw (default: 50)",
    )

    args = parser.parse_args()

    visualizer = UITreeVisualizer()

    # Text tree mode
    if args.text_tree:
        visualizer.print_text_tree(
            xml_path=args.xml,
            filter_type=args.filter,
        )
        return

    # Screenshot overlay mode
    if not args.screenshot:
        parser.error("--screenshot is required for overlay visualization (or use --text-tree for text output).")

    if not HAS_PIL:
        print("PIL/Pillow is required for screenshot visualization. Install with: pip install Pillow")
        sys.exit(1)

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        screenshot_dir = os.path.dirname(args.screenshot) or "."
        screenshot_name = os.path.splitext(os.path.basename(args.screenshot))[0]
        output_path = os.path.join(screenshot_dir, f"visualized_{screenshot_name}.png")

    # Build current_date dict for target day search
    current_date = None
    if args.screenshot_month and args.screenshot_year:
        from datetime import datetime
        current_date = {
            "day": args.screenshot_month or datetime.now().day,
            "month": args.screenshot_month,
            "year": args.screenshot_year,
        }

    # Parse XML using UITreeParser (without device)
    parser_instance = UITreeParser(device_id="dummy")
    visualizer.ui_tree_parser = parser_instance

    visualizer.visualize_screenshot(
        screenshot_path=args.screenshot,
        xml_path=args.xml,
        output_path=output_path,
        target_day=args.target_day,
        current_date=current_date,
        show_labels=not args.no_labels,
        max_labels=args.max_labels,
    )


if __name__ == "__main__":
    main()
