from fastapi import APIRouter

router = APIRouter()


@router.post("/quiz/generate")
async def generate_quiz():
    pass


@router.post("/quiz/submit")
async def submit_quiz():
    pass


@router.post("/flashcards/generate")
async def generate_flashcards():
    pass


@router.post("/essay/grade")
async def grade_essay():
    pass
