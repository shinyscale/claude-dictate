"""
LLM Refinement Prompts for Claude Dictate
Prompts for different text refinement styles.
"""

# Base system prompt for all refinements
SYSTEM_PROMPT = """You are a text editor assistant. Your job is to clean up and refine transcribed speech.
You output ONLY the refined text with no preamble, explanation, or commentary.
Do not include phrases like "Here is the refined text:" or similar."""

# Refinement style prompts
REFINEMENT_PROMPTS = {
    "clean": """Clean up this transcribed speech:
- Fix grammar and punctuation
- Remove filler words (um, uh, like, you know, basically, actually)
- Remove false starts and self-corrections
- Improve sentence flow and readability
- Preserve the original meaning, tone, and personality
- Keep it natural - don't make it sound robotic

Transcription:
{text}

Output only the cleaned text:""",

    "professional": """Transform this transcribed speech into professional writing:
- Fix all grammar, spelling, and punctuation
- Remove all filler words and verbal tics
- Use clear, concise professional language
- Improve structure and organization
- Make it suitable for professional emails or documents
- Maintain the key points and intent

Transcription:
{text}

Output only the professional version:""",

    "technical": """Refine this transcribed speech for technical documentation:
- Fix grammar and use precise technical language
- Remove filler words and casual expressions
- Format for technical clarity
- Use appropriate technical terminology
- Preserve ALL technical details exactly
- Structure logically for documentation

Transcription:
{text}

Output only the technical version:""",

    "casual": """Clean up this transcribed speech while keeping it casual:
- Fix obvious typos and grammar errors
- Remove excessive filler words but keep some for natural flow
- Preserve the conversational, friendly tone
- Keep contractions and casual expressions
- Make it read naturally, like a text message or casual email

Transcription:
{text}

Output only the casual version:""",

    "minimal": """Minimally clean this transcribed speech:
- Fix only clear errors
- Remove only the most excessive filler words
- Keep the speaker's voice and style intact
- Preserve hesitations if they add meaning
- Make minimal changes

Transcription:
{text}

Output only the minimally cleaned text:""",

    "expand": """Expand and elaborate on this transcribed speech:
- Fix grammar and remove filler words
- Expand abbreviated thoughts into full explanations
- Add helpful structure (bullet points, sections) if appropriate
- Clarify any ambiguous statements
- Make it comprehensive while staying true to the original intent

Transcription:
{text}

Output only the expanded version:""",

    "summarize": """Summarize this transcribed speech:
- Extract the key points and main ideas
- Condense into a clear, brief summary
- Remove all tangents and repetition
- Present in logical order
- Keep only essential information

Transcription:
{text}

Output only the summary:""",

    "bullets": """Convert this transcribed speech into bullet points:
- Extract each distinct point or idea
- Format as clear bullet points
- Fix grammar within each point
- Remove filler and redundancy
- Organize logically

Transcription:
{text}

Output only the bullet points:""",

    "prd": """Convert this transcribed speech into product requirements:
- Extract feature requests and requirements
- Identify user stories and acceptance criteria
- Note any technical constraints mentioned
- Organize into clear requirement statements
- Use standard PRD language and structure

Transcription:
{text}

Output the requirements in a structured format:""",

    "prompt": """Convert this transcribed speech into a clear AI prompt:
- Extract the core task or request
- Clarify any ambiguous instructions
- Structure as clear, actionable steps
- Add any implicit context that would help
- Format for use with Claude or other AI assistants

Transcription:
{text}

Output the refined prompt:""",

    "json_prd": """Parse this transcribed speech and identify ALL distinct features, requirements, or test cases mentioned. Output each as a separate JSON object in an array.

For each feature/test case:
- Determine the category (functional, ui, integration, performance, accessibility, etc.)
- Write a clear description of what is being tested or required
- Break down into specific test steps
- Set passes to false (to be updated after testing)

Output ONLY a valid JSON array in this exact format:
[
  {{
    "category": "<category>",
    "description": "<what this test verifies>",
    "steps": [
      "<step 1>",
      "<step 2>",
      "<step 3>"
    ],
    "passes": false
  }}
]

If only one feature is mentioned, still output it as an array with one element.

Transcription:
{text}

Output only the JSON array:""",
}


def get_prompt(style: str, text: str) -> str:
    """
    Get the refinement prompt for a given style.

    Args:
        style: Refinement style name
        text: Text to refine

    Returns:
        Formatted prompt string
    """
    template = REFINEMENT_PROMPTS.get(style, REFINEMENT_PROMPTS["clean"])
    return template.format(text=text)


def get_available_styles() -> list:
    """Get list of available refinement styles."""
    return list(REFINEMENT_PROMPTS.keys())


def get_style_description(style: str) -> str:
    """
    Get a description of a refinement style.

    Args:
        style: Style name

    Returns:
        Human-readable description
    """
    descriptions = {
        "clean": "Fix grammar, remove filler words, improve readability",
        "professional": "Polish for professional communication",
        "technical": "Format for technical documentation",
        "casual": "Keep conversational while fixing errors",
        "minimal": "Make minimal corrections only",
        "expand": "Elaborate and expand on ideas",
        "summarize": "Condense into key points",
        "bullets": "Convert to bullet point format",
        "prd": "Format as product requirements",
        "prompt": "Convert to AI prompt format",
        "json_prd": "Parse features into JSON test cases",
    }
    return descriptions.get(style, "Unknown style")
