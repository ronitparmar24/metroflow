// ============================================================
// GLOBAL FILE:// FETCH INTERCEPTOR
// When HTML pages are opened directly as file://, the browser
// treats relative URLs like /api/stations as file:///C:/api/stations
// which fails with CORS errors. This interceptor transparently
// rewrites any relative URL to http://localhost:5000/... so all
// fetch() calls across every page work without modification.
// ============================================================
(function patchFetchForFileProtocol() {
    if (window.location.protocol !== 'file:') return; // Only applies to file://

    const FLASK_BASE = 'http://localhost:5000';
    const _nativeFetch = window.fetch.bind(window);

    window.fetch = function (input, init) {
        // Rewrite relative URLs (starting with /) to absolute localhost URLs
        if (typeof input === 'string' && input.startsWith('/')) {
            input = FLASK_BASE + input;
        } else if (input instanceof Request && input.url.startsWith('/')) {
            input = new Request(FLASK_BASE + input.url, input);
        }
        return _nativeFetch(input, init);
    };
})();

class MetroAPI {
    constructor() {
        // When opened as file://, relative URLs break — use absolute localhost URL instead
        const isFile = window.location.protocol === 'file:';
        this.baseUrl = (isFile ? 'http://localhost:5000' : '') + '/api';
    }

    // Generic API Call Function
    async call(endpoint, method = 'GET', body = null) {
        const options = {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include' // Important for cookies
        };

        if (body) {
            options.body = JSON.stringify(body);
        }

        try {
            const response = await fetch(`${this.baseUrl}${endpoint}`, options);

            // 1. Parse JSON first (so we can read server error messages)
            let data = {};
            try {
                data = await response.json();
            } catch (err) {
                console.warn('Response was not JSON', err);
            }

            // 2. Handle 401 (Unauthorized)
            if (response.status === 401) {
                // EXCEPTION: If we are trying to Log In, return the failure to the form
                // so it can show "Invalid Password" instead of redirecting.
                if (endpoint === '/login') {
                    return data;
                }

                // Always redirect to the server-hosted login page so cookies work
                const path = window.location.pathname;
                const onProtectedPage = path.includes('dashboard') || path.includes('admin') ||
                    path.includes('profile') || path.includes('ticket');

                if (onProtectedPage || window.location.protocol === 'file:') {
                    window.location.href = 'http://localhost:5000/login.html';
                    throw new Error('Session expired. Redirecting...');
                }

                // If we are on Login/Register page, just return failure silently
                return { success: false, error: 'Not logged in' };
            }

            // 3. Handle General Errors
            // Only throw if the HTTP response was NOT ok AND the server returned an error field.
            // DO NOT throw just because a valid response lacks a 'success' key —
            // some endpoints (analytics, balance, etc.) return plain data objects.
            if (!response.ok && data.error) {
                throw new Error(data.error);
            }

            return data;
        } catch (error) {
            console.error("API Call Failed:", error);
            throw error;
        }
    }

    // Strict Auth Check (For Dashboard)
    async requireAuth() {
        const result = await this.call('/me');
        if (result && result.success) {
            return result.user;
        } else {
            // Use absolute server URL so session cookies work
            window.location.href = 'http://localhost:5000/login.html';
            return null;
        }
    }

    // Passive Auth Check (For Login Page)
    async checkAuth() {
        // We don't catch here anymore because call() handles the silence for us
        const result = await this.call('/me');
        if (result && result.success) {
            // User IS logged in -> Go to Dashboard (use server URL for cookie compatibility)
            const path = window.location.pathname;
            if (path.includes('login.html') || path.includes('register.html') || path === '/' || path.includes('index.html')) {
                window.location.href = 'http://localhost:5000/dashboard.html';
            }
            return result.user;
        }
        return null;
    }

    // --- Helper Functions ---

    formatDate(dateStr) {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
    }

    formatDateTime(dateStr) {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        return date.toLocaleString('en-US', {
            year: 'numeric', month: 'short', day: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });
    }

    showAlert(message, type = 'info') {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} fixed-top m-3 shadow`;
        alertDiv.style.zIndex = '9999';
        alertDiv.innerHTML = `<i class="fas fa-info-circle me-2"></i>${message}`;
        document.body.appendChild(alertDiv);

        setTimeout(() => {
            alertDiv.style.opacity = '0';
            setTimeout(() => alertDiv.remove(), 500);
        }, 3000);
    }



    async logout() {
        try {
            await this.call('/logout', 'POST');
        } catch (err) {
            console.warn("Logout warning:", err);
        } finally {
            // 1. Clear all local data
            localStorage.clear();
            sessionStorage.clear();

            // 2. Remove specific keys just in case
            localStorage.removeItem('metro_logged_in');
            localStorage.removeItem('user_role');
            localStorage.removeItem('username');

            // 3. CRITICAL SECURITY FIX: 
            // Use replace() to remove the current page from history.
            // This prevents the "Back" button from returning to the dashboard.
            window.location.replace('login.html');
        }
    }
}

// 1. Initialize Global API
const API = new MetroAPI();

// 2. BACKWARD COMPATIBILITY (Vital for your Login Page)
// This connects the old "apiCall" function to our new class
window.apiCall = (url, method, body) => API.call(url, method, body);
window.checkAuth = () => API.checkAuth();
window.showAlert = (msg, type) => API.showAlert(msg, type);

// 3. Auto-run Auth Check (Updated to skip Login/Register pages)
document.addEventListener('DOMContentLoaded', () => {
    const path = window.location.pathname;

    // Only check if we are NOT on the auth pages
    // This prevents the 401 error from appearing in the console
    if (!path.includes('login.html') && !path.includes('register.html')) {
        API.checkAuth();
    }
});

// SECURITY: Prevent "Back" button from showing cached pages after logout
window.addEventListener('pageshow', (event) => {
    // If the page is loaded from the "back-forward cache" (bfcache)
    if (event.persisted || (window.performance && window.performance.navigation.type === 2)) {
        window.location.reload();
    }
});