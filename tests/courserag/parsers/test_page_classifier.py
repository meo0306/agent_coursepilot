from courserag.parsers.page_classifier import (
    PageClassificationFeatures,
    PageClassifier,
    PageClassifierProfile,
    extract_page_features,
)


def _features(**overrides: float | int) -> PageClassificationFeatures:
    values: dict[str, float | int] = {
        "native_char_count": 500,
        "printable_ratio": 1.0,
        "garbled_ratio": 0.0,
        "image_area_ratio": 0.0,
        "native_text_area_ratio": 0.5,
    }
    values.update(overrides)
    return PageClassificationFeatures.model_validate(values)


def test_classifier_preserves_three_deterministic_routes() -> None:
    classifier = PageClassifier()

    assert classifier.classify(_features()).mode == "native"
    assert classifier.classify(_features(native_char_count=0, image_area_ratio=1.0)).mode == "ocr"
    assert (
        classifier.classify(
            _features(
                native_char_count=80,
                image_area_ratio=0.8,
                native_text_area_ratio=0.2,
            )
        ).mode
        == "hybrid"
    )


def test_classifier_records_forced_and_unreliable_routes() -> None:
    classifier = PageClassifier()
    forced = classifier.classify(_features(), force_ocr=True)
    unreliable = classifier.classify(_features(printable_ratio=0.5, garbled_ratio=0.3))

    assert forced.mode == "ocr"
    assert forced.rule == "forced_ocr"
    assert forced.metrics["forced_ocr"] == 1.0
    assert unreliable.mode == "ocr"
    assert unreliable.reasons == ("low_printable_ratio", "high_garbled_ratio")
    assert forced.profile_sha256 == classifier.profile.sha256


def test_profile_hash_changes_with_threshold_and_features_are_bounded() -> None:
    first = PageClassifierProfile()
    second = PageClassifierProfile(min_native_chars=31)
    features = extract_page_features(
        "abc\ufffd",
        page_width=100,
        page_height=200,
        image_area=30_000,
        native_text_bboxes=((0, 0, 50, 100),),
    )

    assert first.sha256 != second.sha256
    assert features.native_char_count == 4
    assert features.garbled_ratio == 0.25
    assert features.image_area_ratio == 1.0
    assert features.native_text_area_ratio == 0.25
