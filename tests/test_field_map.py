"""Deterministic field mapping: verified profile values only, never invented ones."""
from __future__ import annotations

from applyforme.field_map import (
    candidate_from_profile,
    map_field,
    map_fields,
    norm,
    unknown_required,
)
from applyforme.models import FieldAnswer, FormField, Preferences, Profile, Tailored


def profile(**over) -> Profile:
    personal = {
        "first_name": "Karthik",
        "last_name": "M",
        "email": "karm@example.com",
        "phone": "+91 90000 00000",
        "location": "Bengaluru, India",
        "linkedin": "https://linkedin.com/in/karthik",
        "github": "https://github.com/karthik",
        "portfolio": "https://karthik.dev",
    }
    personal.update(over.pop("personal", {}))
    data = {
        "personal": personal,
        "resume_path": "./resume.pdf",
        "screening": {
            "work_authorization": "Yes, authorized to work in India",
            "requires_sponsorship": "No",
            "notice_period": "30 days",
            "gender": "Decline to self-identify",
            "veteran_status": "Decline to self-identify",
            "disability_status": "Decline to self-identify",
        },
        "compensation": {"salary_expectation": "50000", "salary_currency": "INR"},
        "preferences": Preferences(current_title="Data Engineer", locations=["Bengaluru, India"]),
        "experience": [{"company": "Acme", "title": "Data Engineer"}],
        "education": [{"school": "MVJCE", "degree": "B.E.", "field": "CSE", "year": "2026"}],
    }
    data.update(over)
    return Profile(**data)


def f(label: str, type: str = "text", **kw) -> FormField:
    key = kw.pop("key", None)
    if key is None:
        f.counter = getattr(f, "counter", 0) + 1
        key = f"f{f.counter - 1}"
    return FormField(key=key, label=label, type=type, **kw)


def test_common_identity_fields_are_mapped_without_an_llm():
    p = profile()
    fields = [
        f("First name*"),
        f("Last name"),
        f("Email address"),
        f("Phone number"),
        f("LinkedIn profile"),
        f("GitHub"),
        f("Portfolio"),
        f("City"),
        f("Resume/CV", "file"),
    ]
    answers = map_fields(fields, p)
    got = {fields[i].key: answers.get(fields[i].key).value for i in range(len(fields))}
    assert got["f0"] == "Karthik"
    assert got["f1"] == "M"
    assert got["f2"] == "karm@example.com"
    assert got["f3"] == "+91 90000 00000"
    assert got["f4"] == "https://linkedin.com/in/karthik"
    assert got["f5"] == "https://github.com/karthik"
    assert got["f6"] == "https://karthik.dev"
    assert got["f7"] == "Bengaluru"
    assert got["f8"] == "RESUME"


def test_missing_phone_is_left_unknown_not_invented():
    p = profile(personal={"phone": ""})
    a = map_field(f("Phone"), candidate_from_profile(p))
    assert a is None


def test_unknown_required_question_is_explicitly_unknown():
    p = profile()
    fields = [f("What is your greatest achievement?*")]
    answers = map_fields(fields, p)
    assert answers == {}
    assert unknown_required(fields, answers) == fields


def test_yes_no_select_coerces_a_profile_sentence():
    p = profile()
    field = f(
        "Are you legally authorized to work in India?",
        "select",
        options=["Select an option", "Yes", "No"],
        required=True,
    )
    a = map_field(field, candidate_from_profile(p))
    assert a is not None and a.value == "Yes"


def test_eeo_question_without_answer_uses_decline_option():
    p = profile(screening={})
    field = f(
        "Gender",
        "select",
        options=["Male", "Female", "Non-binary", "Decline to self-identify"],
    )
    a = map_field(field, candidate_from_profile(p))
    assert a is not None and "decline" in a.value.lower()


def test_invalid_option_is_not_submitted():
    p = profile()
    field = f(
        "Salary expectation",
        "select",
        options=["30,000", "40,000", "50,000"],
    )
    # The profile says 50000; the option labels include commas, and substring
    # matching still finds the right one.
    a = map_field(field, candidate_from_profile(p))
    assert a is not None and a.value == "50,000"


def test_required_asterisk_is_recognized():
    p = profile()
    field = f("Security clearance*")
    assert unknown_required([field], {}) == [field]


def test_consent_checkbox_picks_affirmative_option():
    p = profile()
    field = f(
        "I agree to the privacy policy and terms",
        "checkbox",
        options=["I agree", "I do not agree"],
        required=True,
    )
    a = map_field(field, candidate_from_profile(p))
    assert a is not None and a.value == "I agree"


def test_full_name_and_name_variants_are_not_confused_with_company_name():
    p = profile()
    assert map_field(f("Full name"), candidate_from_profile(p)).value == "Karthik M"
    # "Company name" must not consume the candidate's name.
    assert map_field(f("Company name"), candidate_from_profile(p)) is None


def test_cover_letter_textarea_uses_tailored_letter():
    p = profile()
    t = Tailored(cover_letter="Dear team, I build reliable data pipelines.")
    field = f("Cover letter", "textarea")
    a = map_field(field, candidate_from_profile(p, t))
    assert a is not None and "reliable data pipelines" in a.value


def test_normalization_is_stable():
    assert norm("  First   Name * (required) ") == "first name"
