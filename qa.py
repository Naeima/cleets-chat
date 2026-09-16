"""
qa.py: compatibility module.

Several scripts (app.py, evaluate_answers.py, app_dashboard_with_map.py,
app_integration_example.py, and older dashboard versions) do `import qa` or
`from qa import answer_question`. The QA engine lives in qa_with_humanization.py;
this module re-exports it so both import styles work:

    import qa
    qa.answer_question(kg, question, mode="actual", humanize=False)

    from qa import answer_question_rich, methods_text
"""

from qa_with_humanization import *  # noqa: F401,F403
from qa_with_humanization import (  # noqa: F401
    ONTOLOGY,
    get_client,
    md_links,
    md_table,
    extract_year,
    extract_scenario,
    humanize_answer,
    preserve_sources,
    inventory_answer,
    prediction_answer,
    actual_answer,
    answer_question,
    answer_question_rich,
    methods_text,
    family_label,
    detect_family,
    table_answer,
    wants_table,
)
