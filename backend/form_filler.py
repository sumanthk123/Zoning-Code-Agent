import asyncio
import os
from dotenv import load_dotenv
from browser_use import Agent, Browser
from typing import Optional

load_dotenv()


def get_llm():
    from browser_use import ChatGoogle
    return ChatGoogle(
        model="gemini-2.5-flash-lite",
        api_key=os.getenv('GOOGLE_API_KEY')
    )


def get_request_text(municipality: str) -> str:
    return (
        f"Could you please send me {municipality}'s municipal zoning code as of 1940? "
        f"If a zoning code didn't exist then, could you send me the first post 1940 "
        f"adoption of the zoning code?"
    )


async def fill_and_submit_form(
    form_url: str,
    municipality: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    address: Optional[str] = None,
    phone: Optional[str] = None,
    additional_fields: Optional[dict] = None,
    max_steps: int = 25,
    interactive: bool = True
) -> dict:
    name = name or os.getenv('DEFAULT_NAME', 'John Doe')
    email = email or os.getenv('DEFAULT_EMAIL', 'test@example.com')
    address = address or os.getenv('DEFAULT_ADDRESS', '123 Main St, City, State, ZIP')
    phone = phone or os.getenv('DEFAULT_PHONE', '')
    additional_fields = additional_fields or {}
    request_text = get_request_text(municipality)

    field_list = f"""
    Name: {name}
    Email: {email}
    Address: {address}"""

    if phone:
        field_list += f"\n    Phone: {phone}"

    field_list += f"\n    Request Description: {request_text}"

    for field_name, field_value in additional_fields.items():
        field_list += f"\n    {field_name}: {field_value}"

    task = f"""
    - Your goal is to fill out and submit a public records request form with the provided information.
    - Navigate to {form_url}
    - Scroll through the entire form and use extract_structured_data action to extract all the relevant information needed to fill out the form. Use this information and return a structured output that can be used to fill out the entire form with these details: {field_list}. Use the done action to finish the task.

    - Follow these instructions carefully:
        - If anything pops up that blocks the form (cookie banners, dialogs, etc.), close it out and continue filling out the form.
        - Do not skip any fields, even if they are optional. If you do not have the information, make your best educated guess based on the information provided.
        - Fill out the form from top to bottom, never skip a field to come back to it later.
        - When filling out a field, only focus on one field per step.
        - For each step, scroll to the related field before interacting with it.

    These are the general steps (adapt based on what fields you find in the form):
        1) Use input_text action to fill out text fields like:
            - Name: {name}
            - Email: {email}
            - Address: {address}
            - Phone: {phone}"""

    task += f"""
            - Request/Description/Subject: {request_text}

            For DATE/CALENDAR FIELDS (like "Date Range From", "Date Range To"):
            - First attempt: Type the date directly in format MM/DD/YYYY (e.g., "01/01/1940")
            - If typing doesn't work: Click the calendar icon, then navigate and click the date
            - For historical zoning requests, use date range: 01/01/1940 to 12/31/1945
            - Always fill both "From" and "To" dates if present

        2) Use click action to select any dropdown options, radio buttons, or checkboxes:
            - If asked about request type, select "Public Records Request" or similar
            - If asked about preferred delivery method, select "Email" if available
            - Fill out ALL dropdowns and selections, making educated guesses based on context

        3) Use input_text action to fill out any additional fields:"""

    for field_name, field_value in additional_fields.items():
        task += f"""
            - {field_name}: {field_value}"""

    task += f"""

        4) CLICK THE SUBMIT BUTTON AND CHECK FOR A SUCCESS SCREEN. Once there is a success screen or confirmation message, complete your end task.

    - Before you start, create a step-by-step plan to complete the entire task. Make sure to delegate a step for each field to be filled out.

    *** IMPORTANT ***:
        - Before completing every step, refer to this information for accuracy. It is structured in a way to help you fill out the form and is the source of truth.
        - You are not done until you have filled out EVERY field of the form (both required AND optional).
        - When you have completed the entire form, press the submit button to submit the request and use the done action once you have confirmed submission.
        - Make educated guesses for any fields not explicitly provided. For example:
            * Organization: Use "Individual" or "Private Citizen" if not provided
            * Preferred contact method: Use "Email"
            * Date needed by: Use "No rush" or leave blank
            * Purpose of request: Use "Research" or "Historical records"
        - If you encounter a CAPTCHA, stop immediately and report it - do NOT attempt to solve it.
        - If the form requires login/account creation, stop immediately and report it.
        - If the page is just a PDF download link (not a web form), stop immediately and report it.
        - At the end of the task, structure your final_result as:
            1) A human-readable summary of all fields filled and actions performed
            2) A list of all form fields encountered with their values
            3) Confirmation of whether the submission was successful
            Do not say "see above." Include a fully written out, human-readable summary at the very end.
    """

    print(f"Target: {municipality}")
    print(f"Form URL: {form_url}")
    print(f"Email: {email}")
    print(f"Request: {request_text[:80]}...")

    llm = get_llm()
    browser = Browser(
	    headless=True,
	    window_size={'width': 1000, 'height': 700},
    )
    agent = Agent(task=task, llm=llm, use_vision="auto", browser=browser)

    print("Starting agent...")
    result = await agent.run(max_steps=max_steps)

    print("Agent completed!")

    return {
        'success': True,
        'municipality': municipality,
        'form_url': form_url,
        'result': result,
        'error': None,
    }


async def main():
    result = await fill_and_submit_form(
        form_url="https://portal.laserfiche.com/n6789/forms/PRA",
        municipality="Town of Blackstone"
    )

    print("\nFinal Result:")
    print(f"  Success: {result['success']}")
    if result['error']:
        print(f"  Error: {result['error']}")


if __name__ == "__main__":
    asyncio.run(main())
