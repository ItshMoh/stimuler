from pydantic import BaseModel


class Prompt(BaseModel):
    id: str
    text: str
    category: str
    difficulty: str


PROMPTS: list[Prompt] = [
    Prompt(
        id="ielts_daily_routine_1",
        text="I usually start my day with a short walk and a cup of tea.",
        category="IELTS",
        difficulty="easy",
    ),
    Prompt(
        id="ielts_city_life_1",
        text="Living in a busy city can be exciting, but it can also feel stressful.",
        category="IELTS",
        difficulty="medium",
    ),
    Prompt(
        id="professional_intro_1",
        text="Hello, I am Michael from Philadelphia, and I work as a product designer.",
        category="Professional",
        difficulty="easy",
    ),
    Prompt(
        id="professional_update_1",
        text="The project is on track, and we expect to finish the first milestone this week.",
        category="Professional",
        difficulty="medium",
    ),
]


def get_prompt(prompt_id: str) -> Prompt | None:
    return next((prompt for prompt in PROMPTS if prompt.id == prompt_id), None)
