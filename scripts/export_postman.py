import json
from pathlib import Path
from app.main import app


def convert():
    spec = app.openapi()
    items = []
    for path, methods in spec.get('paths', {}).items():
        for method, operation in methods.items():
            if method.lower() not in {'get','post','put','patch','delete'}:
                continue
            raw = '{{base_url}}' + path
            for parameter in operation.get('parameters', []):
                if parameter.get('in') == 'path':
                    raw = raw.replace('{' + parameter['name'] + '}', '{{' + parameter['name'] + '}}')
            request = {
                'method': method.upper(),
                'header': [
                    {'key': 'Authorization', 'value': 'Bearer {{access_token}}', 'type': 'text'},
                    {'key': 'Content-Type', 'value': 'application/json', 'type': 'text'},
                ],
                'url': {'raw': raw, 'host': ['{{base_url}}'], 'path': [p for p in path.strip('/').split('/') if p]},
            }
            content = operation.get('requestBody', {}).get('content', {}).get('application/json', {})
            if content:
                request['body'] = {'mode': 'raw', 'raw': '{}', 'options': {'raw': {'language': 'json'}}}
            items.append({'name': operation.get('summary') or f'{method.upper()} {path}', 'request': request})
    collection = {
        'info': {
            '_postman_id': 'enterprise-cms-api',
            'name': 'Enterprise Headless CMS API',
            'schema': 'https://schema.getpostman.com/json/collection/v2.1.0/collection.json',
        },
        'variable': [
            {'key': 'base_url', 'value': 'http://127.0.0.1:8000'},
            {'key': 'access_token', 'value': ''},
        ],
        'item': items,
    }
    Path('postman_collection.json').write_text(json.dumps(collection, indent=2), encoding='utf-8')
    print(f'Wrote postman_collection.json with {len(items)} requests')


if __name__ == '__main__':
    convert()
