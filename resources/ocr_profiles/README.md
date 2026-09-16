# P05 OCR profiles

The three candidate profiles fix the approved 200 DPI / 20 MP / 60 second / 1.5 GiB
resource envelope. Their checked-in model manifests are deliberately `unresolved`: they describe
the candidate distribution but do not pretend that model files have been downloaded or hashed.

The isolated image must create a `resolved` manifest containing at least one exact artifact Hash,
then create a runtime copy of the profile bound to that manifest. The provider adapters fail
closed on unresolved, missing, or mismatched manifests.

The owner approved RapidOCR as `default_v1` after the three-engine Pilot. The selected profile
keeps 200 DPI, 20 MP, 1.5 GiB and one Worker, while increasing the per-page hard timeout from 60
to 90 seconds. Its checked-in model manifest remains unresolved by design; image construction
must create a resolved runtime copy with exact model-file Hashes. Tesseract and PaddleOCR remain
evaluation candidates and are never automatic fallbacks.
