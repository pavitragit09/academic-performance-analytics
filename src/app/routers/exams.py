"""Faculty API for exam results (APAS-F-013, SAD Table 14)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from src.app import exam_results as exams
from src.app.database import get_db

router = APIRouter(tags=["exams"])


@router.post(
    "/courses/{course_id}/exams",
    response_model=exams.UploadReport,
    status_code=status.HTTP_201_CREATED,
)
def upload_exam_results(course_id: int, data: exams.ExamUpload, db: Session = Depends(get_db)):
    return exams.save_exam_results(db, course_id, data)


@router.get("/courses/{course_id}/exams", response_model=exams.CourseExams)
def get_exam_results(course_id: int, exam_type: exams.ExamType, db: Session = Depends(get_db)):
    return exams.course_exam_results(db, course_id, exam_type)