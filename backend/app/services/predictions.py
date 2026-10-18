"""Normalize historical weighted confidences without rewriting saved detections."""


def normalize_predictions(predictions, media_type):
    def normalize(item):
        item = dict(item)
        if "raw_confidence" in item:
            item.setdefault("ranking_score", item.get("confidence", 0))
            item["confidence"] = item["raw_confidence"]
        return item
    if media_type == "video":
        return [{**event, "detections": [normalize(p) for p in event.get("detections", [])]}
                for event in (predictions or [])]
    return [normalize(p) for p in (predictions or [])]
