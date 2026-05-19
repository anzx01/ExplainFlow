import json
from pathlib import Path
from src.explain.models import ExplainGraph
from src.planner.models import Storyboard
from src.planner.service import _contains_semiconductor_topic, _graph_source_corpus, _ensure_storyboard_quality

root = Path('../..').resolve()
raw_graph = json.loads((root / '.tmp/e2e_visual_grammar/graph.json').read_text(encoding='utf-8-sig'))['graph']
raw_story = json.loads((root / '.tmp/e2e_visual_grammar/storyboard.json').read_text(encoding='utf-8-sig'))['storyboard']
graph = ExplainGraph.model_validate(raw_graph)
story = Storyboard.model_validate(raw_story)
source = _graph_source_corpus(graph)
full = ' '.join([source, json.dumps(raw_story, ensure_ascii=False)]).lower()
print('source_has_semiconductor=', _contains_semiconductor_topic(source))
print('full_has_semiconductor=', _contains_semiconductor_topic(full))
fixed = _ensure_storyboard_quality(story, graph, 120)
print('fixed scenes=', len(fixed.scenes), 'total=', fixed.total_duration_estimate)
for s in fixed.scenes:
    print(s.order, s.title, s.diagram_plan.kind if s.diagram_plan else None)
