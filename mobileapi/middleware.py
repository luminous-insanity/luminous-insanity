class MobileApiNoStoreMiddleware:
    """Prevent shared/browser caches from storing authenticated mobile API data."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith('/api/v1/'):
            response['Cache-Control'] = 'no-store, private'
            response['Pragma'] = 'no-cache'
            response['Vary'] = ', '.join(filter(None, [response.get('Vary', ''), 'Authorization']))
        return response
