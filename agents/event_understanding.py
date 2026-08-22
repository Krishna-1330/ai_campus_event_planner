from services.gemini_service import extract_requirements


def run(prompt, gemini_key=""):
    return extract_requirements(prompt, gemini_key)
