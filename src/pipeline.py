"""Integrated compliance screening pipeline orchestrating visual gating, OCR, rules, and arbitration."""

from typing import List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field

from src.decisions.arbiter import DecisionArbiter
from src.decisions.models import ScreeningDecision
from src.evidence.generator import EvidenceGenerator
from src.evidence.models import EvidenceDossier
from src.extraction.models import ProductDeclarations
from src.extraction.parser import DeclarationParser
from src.image_quality.models import ImageQualityMetrics
from src.image_quality.processor import ImageQualityChecker
from src.ocr.engine import OCRService
from src.ocr.gemini_extractor import GeminiPerceptionService, load_gemini_api_key
from src.ocr.models import OCRResult
from src.regulatory.knowledge_base import RegulatoryKnowledgeBase
from src.rules.engine import LegalMetrologyRuleEngine
from src.rules.models import RuleEvaluationResult


class PipelineResult(BaseModel):
    """End-to-end compliance screening pipeline outcome."""

    model_config = ConfigDict(frozen=True)

    quality_metrics: ImageQualityMetrics = Field(
        ..., description="Optical image quality assessment results"
    )
    ocr_result: OCRResult = Field(
        ..., description="Extracted OCR text lines, confidence, and bounding boxes"
    )
    declarations: ProductDeclarations = Field(
        ..., description="Normalized structured statutory product declarations"
    )
    rule_results: list[RuleEvaluationResult] = Field(
        ..., description="Deterministic statutory compliance evaluation results"
    )
    evidence_dossier: EvidenceDossier = Field(
        ..., description="Cryptographically hashed visual evidence crops for infractions"
    )
    decision: ScreeningDecision = Field(
        ..., description="Final Three-State regulatory screening verdict"
    )
    gemini_error: Optional[str] = Field(
        default=None,
        description="Diagnostic error message if Gemini multimodal perception failed and fell back to local OCR",
    )


class CompliancePipeline:
    """Unified pipeline orchestrator executing end-to-end package screening."""

    def __init__(
        self,
        tesseract_cmd: Optional[str] = None,
        kb: Optional[RegulatoryKnowledgeBase] = None,
        gemini_api_key: Optional[str] = None,
        gemini_service: Optional[GeminiPerceptionService] = None,
    ) -> None:
        """Initializes all sub-services for the compliance screening pipeline."""
        self.quality_checker = ImageQualityChecker()
        self.ocr_service = OCRService(tesseract_cmd=tesseract_cmd)
        self.parser = DeclarationParser()
        self.kb = kb if kb is not None else RegulatoryKnowledgeBase()
        self.rule_engine = LegalMetrologyRuleEngine(kb=self.kb)
        self.evidence_gen = EvidenceGenerator()
        self.arbiter = DecisionArbiter()
        self.last_gemini_error: Optional[str] = None

        if gemini_service:
            self.gemini_service = gemini_service
        elif gemini_api_key:
            self.gemini_service = GeminiPerceptionService(api_key=gemini_api_key)
        else:
            self.gemini_service = None

    def set_injected_text(self, lines: Optional[list[str]]) -> None:
        """Helper to inject synthetic text into the OCR service for testing or simulation."""
        self.ocr_service.set_injected_text(lines)

    def process_image(self, image_bytes: Union[bytes, List[bytes]]) -> PipelineResult:
        """Executes full compliance screening on a raw package image or list of multi-angle images."""
        return self.process_package(image_bytes)

    def process_images(self, images: List[bytes]) -> PipelineResult:
        """Executes full compliance screening on a list of multi-angle package images."""
        return self.process_package(images)

    def process_package(self, image_bytes: Union[bytes, List[bytes]]) -> PipelineResult:
        """Executes full compliance screening on single or multi-angle package image payloads.

        Args:
            image_bytes: Raw binary image payload or list of binary image payloads (multi-angle).

        Returns:
            An immutable PipelineResult instance.

        Raises:
            ValueError: If image bytes are corrupted, empty, or unreadable.
        """
        raw_images: list[bytes] = (
            list(image_bytes) if isinstance(image_bytes, (list, tuple)) else [image_bytes]
        )
        if not raw_images:
            raise ValueError("No image payloads provided to pipeline.")

        print(f"[DEBUG PIPELINE EXEC] gemini_service present: {self.gemini_service is not None}, images count: {len(raw_images)}")

        # Step 1: Image Quality Assessment Gate across all angles
        bgr_imgs = []
        qualities = []
        for img_b in raw_images:
            b_img, q = self.quality_checker.assess_quality(img_b)
            bgr_imgs.append(b_img)
            qualities.append(q)

        # Compute aggregate / worst-case quality metrics to preserve optical integrity
        if len(qualities) == 1:
            quality = qualities[0]
        else:
            min_sharp = min(q.laplacian_variance for q in qualities)
            max_glare = max(q.glare_ratio for q in qualities)
            is_all_sharp = all(q.is_sharp for q in qualities) and (min_sharp >= 80.0)
            is_all_acceptable_glare = all(q.has_acceptable_glare for q in qualities) and (max_glare <= 0.05)
            is_acceptable = is_all_sharp and is_all_acceptable_glare

            all_warnings: list[str] = []
            for idx, q in enumerate(qualities, 1):
                for w in q.quality_warnings:
                    pref = f"Angle {idx}: {w}"
                    if pref not in all_warnings:
                        all_warnings.append(pref)

            quality = ImageQualityMetrics(
                width=min(q.width for q in qualities),
                height=min(q.height for q in qualities),
                laplacian_variance=min_sharp,
                glare_ratio=max_glare,
                is_sharp=is_all_sharp,
                has_acceptable_glare=is_all_acceptable_glare,
                is_acceptable_for_screening=is_acceptable,
                quality_warnings=all_warnings,
            )

        bgr_img = bgr_imgs[0]

        # Step 2 & 3: Perception & Structured Extraction
        decls: Optional[ProductDeclarations] = None
        ocr_res: Optional[OCRResult] = None
        gemini_error: Optional[str] = None

        # Prefer Gemini multimodal perception service if available and no synthetic injected text is set
        if (
            self.gemini_service is not None
            and self.gemini_service.is_available()
            and not self.ocr_service.injected_text
        ):
            try:
                decls, ocr_res = self.gemini_service.extract(raw_images)
                self.last_gemini_error = None
            except Exception as exc:
                import traceback

                traceback.print_exc()
                print(f"[DEBUG PIPELINE FALLBACK TRIGGERED]: {exc}")
                self.last_gemini_error = str(exc)
                gemini_error = str(exc)
                decls = None
                ocr_res = None
        elif self.gemini_service is None or not self.gemini_service.is_available():
            if not self.ocr_service.injected_text:
                gemini_error = "GEMINI_API_KEY is not configured or available."
                self.last_gemini_error = gemini_error

        # Seamless fallback to local OCRService + DeclarationParser
        if decls is None or ocr_res is None:
            if len(bgr_imgs) == 1:
                ocr_res = self.ocr_service.extract_text(bgr_imgs[0])
            else:
                all_lines = []
                all_transcripts = []
                total_conf = 0.0
                engine_used = "PYTESSERACT"
                for b_sub in bgr_imgs:
                    sub_res = self.ocr_service.extract_text(b_sub)
                    engine_used = sub_res.engine_used
                    all_lines.extend(sub_res.lines)
                    all_transcripts.append(sub_res.full_text)
                    total_conf += sub_res.mean_confidence
                mean_conf = round(total_conf / len(bgr_imgs), 3) if bgr_imgs else 0.0
                ocr_res = OCRResult(
                    lines=all_lines,
                    full_text="\n".join(all_transcripts),
                    mean_confidence=mean_conf,
                    engine_used=engine_used,
                )
            decls = self.parser.extract_all(ocr_res)

        # Step 4: Deterministic Statutory Rule Evaluation
        rules = self.rule_engine.evaluate(
            decls, is_quality_acceptable=quality.is_acceptable_for_screening
        )

        # Step 5: Visual Evidence Crop & Cryptographic Dossier Generation
        evidence = self.evidence_gen.generate_dossier(bgr_img, decls, rules)

        # Step 6: Three-State Decision Arbitration
        decision = self.arbiter.adjudicate(rules, quality, ocr_res.mean_confidence)

        return PipelineResult(
            quality_metrics=quality,
            ocr_result=ocr_res,
            declarations=decls,
            rule_results=rules,
            evidence_dossier=evidence,
            decision=decision,
            gemini_error=gemini_error,
        )
