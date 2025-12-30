class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # 1. Content Security Policy (CSP) - Basic Protection
        # Allows self, data images (for logos), and inline styles (needed for Flowbite/Tailwind usually)
        # Prevents loading malicious scripts from external sites.
        csp_policy = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; " # unsafe-inline/eval often needed for HTMX/Alpine without nonces
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )
        response['Content-Security-Policy'] = csp_policy

        # 2. Permissions Policy (formerly Feature Policy)
        # Disables powerful browser features that the app doesn't need, reducing attack surface.
        permissions = (
            "accelerometer=(), "
            "camera=(), "
            "geolocation=(), "
            "gyroscope=(), "
            "magnetometer=(), "
            "microphone=(), "
            "payment=(), "
            "usb=()"
        )
        response['Permissions-Policy'] = permissions

        # 3. Referrer Policy
        # Controls how much information is sent to external sites when linking out.
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        return response
