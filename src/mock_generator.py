"""Synthetic packaging label generator for testing and validation."""

from pathlib import Path
import cv2
import numpy as np


class SyntheticPackageGenerator:
    """Generates synthetic high-contrast package labels for compliance testing."""

    COMPLIANT_TEXT: list[str] = [
        "BRIT-BAKE COOKIES",
        "Net Qty: 500 g",
        "MRP Rs. 150.00 (Incl. of all taxes)",
        "USP Rs. 0.30 / g",
        "Mfg Date: 09/2026",
        "Consumer Care: care@britbake.com, Tel: 1800-111-222",
    ]

    UNIT_VIOLATION_TEXT: list[str] = [
        "BRIT-BAKE COOKIES",
        "Net Wt: 500 gms",
        "MRP Rs. 150.00 (Incl. of all taxes)",
        "Mfg Date: 09/2026",
        "Consumer Care: care@britbake.com",
    ]

    MRP_VIOLATION_TEXT: list[str] = [
        "BRIT-BAKE COOKIES",
        "Net Qty: 500 g",
        "MRP Rs. 150.00",
        "Mfg Date: 09/2026",
    ]

    def _render_label(self, lines: list[str], width: int = 800, height: int = 600) -> bytes:
        """Renders an array of text lines onto a label canvas and encodes as PNG bytes.
        
        Background is set to luminance 240 (light packaging card/paper) to prevent
        triggering false specular glare alerts (>250 cutoff) while preserving high contrast.
        """
        canvas = np.full((height, width, 3), 240, dtype=np.uint8)

        # Draw a simulated border around the package label
        cv2.rectangle(canvas, (20, 20), (width - 20, height - 20), (50, 50, 50), 2)

        start_y = 90
        line_spacing = 75
        for idx, line in enumerate(lines):
            y = start_y + (idx * line_spacing)
            font_scale = 1.0 if idx == 0 else 0.75
            thickness = 2
            cv2.putText(
                canvas,
                line,
                (50, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                (10, 10, 10),
                thickness,
                cv2.LINE_AA,
            )

        success, encoded = cv2.imencode(".png", canvas)
        if not success:
            raise RuntimeError("Failed to encode synthetic label image to PNG format.")
        return encoded.tobytes()

    def generate_compliant_label(self) -> bytes:
        """Generates a fully compliant synthetic packaging label."""
        return self._render_label(self.COMPLIANT_TEXT)

    def generate_unit_violation_label(self) -> bytes:
        """Generates a synthetic label bearing a prohibited unit symbol ('gms')."""
        return self._render_label(self.UNIT_VIOLATION_TEXT)

    def generate_mrp_tax_violation_label(self) -> bytes:
        """Generates a synthetic label missing the compulsory tax-inclusive statement."""
        return self._render_label(self.MRP_VIOLATION_TEXT)

    def save_samples_to_disk(self, target_dir: str = "data/samples") -> dict[str, str]:
        """Generates and writes standard sample label images to the target directory.

        Args:
            target_dir: Destination folder path (defaults to 'data/samples').

        Returns:
            Dictionary mapping sample keys to saved absolute file paths.
        """
        dest_path = Path(target_dir).resolve()
        dest_path.mkdir(parents=True, exist_ok=True)

        samples = {
            "sample_compliant.png": self.generate_compliant_label(),
            "sample_violation_units.png": self.generate_unit_violation_label(),
            "sample_violation_mrp.png": self.generate_mrp_tax_violation_label(),
        }

        saved_paths: dict[str, str] = {}
        for filename, img_bytes in samples.items():
            file_path = dest_path / filename
            file_path.write_bytes(img_bytes)
            saved_paths[filename] = str(file_path)

        return saved_paths


if __name__ == "__main__":
    generator = SyntheticPackageGenerator()
    saved = generator.save_samples_to_disk()
    print(f"Successfully generated {len(saved)} synthetic sample images:")
    for name, path in saved.items():
        print(f"  - {name} -> {path}")
