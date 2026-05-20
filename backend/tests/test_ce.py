import asyncio, json
from app.services.document_service import document_service
res = asyncio.run(document_service.search_similar(
    'summarize CIRCUIT_SYSTEM_SOLUTIONS.DOCX',
    query_class='RAG_QUERY'
))
print('guard_triggered:', res.get('guard_triggered'))
print('confidence:', res.get('confidence_level'))
print('num chunks:', len(res.get('results', [])))
for r in res.get('results', []):
    sim = r['similarity']
    cnt = r['content'][:60]
    print(f'  sim={sim:.3f} | {cnt}...')
