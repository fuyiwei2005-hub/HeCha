from pydantic import BaseModel


class ClassCount(BaseModel):
    name: str
    name_cn: str = ""
    count: int


class StatisticsResponse(BaseModel):
    total_jobs: int
    image_jobs: int
    video_jobs: int
    completed_jobs: int
    failed_jobs: int
    total_objects: int
    classes: list[ClassCount]
