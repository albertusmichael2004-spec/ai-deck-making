from datetime import datetime,timezone,timedelta

import pytest

from preferences.classification import classify
from preferences.store import PreferenceStore
from state.errors import StudioError


@pytest.mark.parametrize("text,kind",[("Change 20% to 25%","FACTUAL_CORRECTION"),("Wrong number in the chart","FACTUAL_CORRECTION"),("Use the new CSV data","DATA_UPDATE"),("Add a slide about execution","NEW_REQUIREMENT"),("Use the corporate brand logo","BRAND_CHANGE"),("Only this selected object should change","SCOPE_CHANGE"),("Make the wording concise","COPY_PREFERENCE"),("This layout is too crowded","DESIGN_FEEDBACK")])
def test_feedback_intent_classification(text,kind):assert classify(text)["type"]==kind


def test_numeric_corrections_cannot_poison_design_preferences(repo):
    store=PreferenceStore(repo)
    result=store.record("Change 20% to 25%","single_exhibit",event_id="factual",declared_type="DESIGN_FEEDBACK",polarity="negative")
    assert result["event"]["type"]=="FACTUAL_CORRECTION" and result["event"]["polarity"]=="neutral"
    assert store.score("single_exhibit")["score"]==0 and store.state()["records"]=={}
    assert classify("Change font 20 to 25")["type"]=="DESIGN_FEEDBACK"


def test_idempotent_modest_contextual_learning_and_conflict(repo):
    store=PreferenceStore(repo);context={"user_id":"alber","brand":"acme","project_id":"p1"}
    first=store.record("This layout is clear and good","two_column",context=context,event_id="approval",polarity="positive")
    assert store.record("This layout is clear and good","two_column",context=context,event_id="approval",polarity="positive")["status"]=="unchanged"
    score=store.score("two_column",context);assert .3<score["score"]<.34 and score["sample_count"]==1
    assert store.score("two_column",{"user_id":"someone_else","brand":"acme","project_id":"p1"})["score"]==0
    assert store.score("two_column",{"user_id":"alber","brand":"other","project_id":"p1"})["score"]==0
    with pytest.raises(StudioError):store.record("Different feedback","two_column",context=context,event_id="approval")


def test_weak_implicit_repetition_recency_reset_and_override(repo):
    store=PreferenceStore(repo)
    store.record("Pattern removed","cards",event_id="implicit",signal="pattern_removed")
    assert -.12<store.score("cards")["score"]<0
    old=(datetime.now(timezone.utc)-timedelta(days=360)).isoformat()
    store.record("This card layout is too crowded","cards",event_id="old",occurred_at=old,polarity="negative")
    for index in range(4):store.record("This card layout is too crowded","cards",event_id="reject_"+str(index),polarity="negative")
    assert store.score("cards")["score"]<-.6
    store.reset("cards");assert store.score("cards")["score"]==0
    store.record("This card design is good","cards",event_id="after_reset",polarity="positive")
    assert store.score("cards")["score"]>0
    store.override("cards",-.9);assert store.score("cards")["score"]==-.9
    store.reset("cards");assert store.score("cards")["score"]==0


def test_deprecated_patterns_and_reranking_preserve_candidate_data(repo):
    store=PreferenceStore(repo);store.record("Never use this layout again","cards",event_id="deprecate")
    assert store.score("cards")["deprecated"]
    choices=[{"pattern":"cards","score":.9,"data":[20,25]},{"pattern":"single_exhibit","score":.8,"data":[20,25]}]
    ranked=store.rerank(choices);assert ranked[0]["pattern"]=="single_exhibit" and all(row["data"]==[20,25] for row in ranked)
    assert choices[0]["score"]==.9


def test_adaptive_layout_learning_obeys_density_and_explicit_archetype(repo,project):
    import importlib.util
    from pathlib import Path
    from layout.adaptive import AdaptiveLayoutCompiler
    spec=importlib.util.spec_from_file_location("preference_layout_case",Path(__file__).parents[1]/"fixtures/consulting_exhibits.py");case=importlib.util.module_from_spec(spec);spec.loader.exec_module(case)
    brief,deck,slides,evidence,store=case.prepare(repo,project,types=("bar",));slide=slides[0];slide["exhibit"]=evidence.resolve_exhibit(slide);slide["layout"]["archetype"]="auto";slide["insights"]=["Validate root causes before action."]
    preferences=PreferenceStore(repo);layout=AdaptiveLayoutCompiler(repo,preferences)
    assert layout.compile(deck,slide)["resolved_archetype"]=="two_column"
    for index in range(3):preferences.record("This two column layout is too crowded","two_column",event_id="negative"+str(index),polarity="negative")
    assert layout.compile(deck,slide)["resolved_archetype"]=="single_exhibit"
    slide["layout"]["archetype"]="two_column";assert layout.compile(deck,slide)["resolved_archetype"]=="two_column"


def test_reference_reranking_uses_preferences_without_mutating_provenance(repo):
    import importlib.util
    from pathlib import Path
    from references.store import ReferenceStore
    spec=importlib.util.spec_from_file_location("preference_reference_case",Path(__file__).with_name("test_reference_store.py"));case=importlib.util.module_from_spec(spec);spec.loader.exec_module(case)
    source,_=case.create_reference(repo);preferences=PreferenceStore(repo);store=ReferenceStore(repo,case.FixtureRenderer(repo),preferences);store.ingest()
    initial=store.query({"text":""});selected=initial[-1];pattern=selected["pattern"]
    preferences.override(pattern,1)
    ranked=store.query({"text":""});assert ranked[0]["pattern"]==pattern and ranked[0]["preference"]["override"]
    original=store.load(selected["reference_id"],selected["slide_id"],"original");assert original["sha256"]==store.state()["decks"][selected["reference_id"]]["file_sha256"]
