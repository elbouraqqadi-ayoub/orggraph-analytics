param([switch]$Gui)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
python -X utf8 -m orgkg ingest
if ($LASTEXITCODE -ne 0) { throw 'Échec de l’ingestion' }
python -X utf8 -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Échec des tests' }
python -X utf8 -c "from pathlib import Path; import json; from orgkg.pipeline import benchmark; g=json.loads(Path('data/graph.json').read_text(encoding='utf-8')); r=benchmark(g,Path('evaluation/questions.json'),Path('output/benchmark.json')); print('F1 de recherche sur corpus synthétique :', r['mean_retrieval_f1'])"
if ($LASTEXITCODE -ne 0) { throw 'Échec du benchmark' }
if ($Gui) { python -X utf8 -m orgkg gui }
