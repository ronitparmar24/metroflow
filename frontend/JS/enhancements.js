/* ═══════════════════════════════════════════════════════════════════════
   METROFLOW ENHANCEMENTS — Round 3 JavaScript
   Toast · Confetti · CountUp · Ripple · Greeting · Suggestions · Carbon
   ═══════════════════════════════════════════════════════════════════════ */
(function () {
    'use strict';

    window.addEventListener('DOMContentLoaded', () => {
        setTimeout(initEnhancements, 1500);
    });

    function initEnhancements() {
        injectToastContainer();
        initRippleEffects();
        initScrollReveal();
        upgradeGreeting();
        loadSmartSuggestions();
        loadActivityFeed();
        enhanceChatbot();
        enhanceCoachSelector();
        enhanceWalletChips();
        initCrowdIndicators();
        initAnimatedCounters();
    }

    // ═══════════════════════════════════════════════════════════════
    //  1. PREMIUM TOAST SYSTEM (replaces basic alerts)
    // ═══════════════════════════════════════════════════════════════
    function injectToastContainer() {
        if (document.getElementById('toastContainerCustom')) return;
        const c = document.createElement('div');
        c.className = 'toast-container-custom';
        c.id = 'toastContainerCustom';
        document.body.appendChild(c);
    }

    const TOAST_ICONS = {
        success: '<i class="fas fa-check-circle"></i>',
        error: '<i class="fas fa-exclamation-circle"></i>',
        warning: '<i class="fas fa-exclamation-triangle"></i>',
        info: '<i class="fas fa-info-circle"></i>'
    };

    window.showToast = function (msg, type = 'info', duration = 4000) {
        const container = document.getElementById('toastContainerCustom');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = 'toast-custom';
        toast.innerHTML = `
            <div class="toast-icon ${type}">${TOAST_ICONS[type] || TOAST_ICONS.info}</div>
            <div class="toast-content">
                <p class="toast-title">${type.charAt(0).toUpperCase() + type.slice(1)}</p>
                <p class="toast-msg">${msg}</p>
            </div>
            <button class="toast-close" onclick="this.parentElement.classList.add('removing');setTimeout(()=>this.parentElement.remove(),300)">
                <i class="fas fa-times"></i>
            </button>
            <div class="toast-progress ${type}" style="animation-duration:${duration}ms"></div>
        `;
        container.appendChild(toast);

        setTimeout(() => {
            if (toast.parentElement) {
                toast.classList.add('removing');
                setTimeout(() => toast.remove(), 300);
            }
        }, duration);
    };

    // ═══════════════════════════════════════════════════════════════
    //  2. CONFETTI CELEBRATION
    // ═══════════════════════════════════════════════════════════════
    window.launchConfetti = function () {
        const container = document.createElement('div');
        container.className = 'confetti-container';
        document.body.appendChild(container);

        const colors = ['#667eea', '#764ba2', '#f093fb', '#f5576c', '#4facfe', '#22c55e', '#f59e0b', '#ef4444'];

        for (let i = 0; i < 60; i++) {
            const piece = document.createElement('div');
            piece.className = 'confetti-piece';
            piece.style.left = Math.random() * 100 + '%';
            piece.style.animationDuration = (2 + Math.random() * 2) + 's';
            piece.style.animationDelay = Math.random() * 0.5 + 's';
            piece.style.background = colors[Math.floor(Math.random() * colors.length)];
            piece.style.borderRadius = Math.random() > 0.5 ? '50%' : '2px';
            piece.style.width = (6 + Math.random() * 8) + 'px';
            piece.style.height = (6 + Math.random() * 8) + 'px';
            container.appendChild(piece);
        }

        setTimeout(() => container.remove(), 4000);
    };

    // ═══════════════════════════════════════════════════════════════
    //  3. BUTTON RIPPLE EFFECT
    // ═══════════════════════════════════════════════════════════════
    function initRippleEffects() {
        document.addEventListener('click', function (e) {
            const btn = e.target.closest('.btn-gradient, .suggestion-action-btn, .pass-buy-btn, .quick-action-btn');
            if (!btn) return;

            const rect = btn.getBoundingClientRect();
            const ripple = document.createElement('span');
            ripple.className = 'ripple-effect';
            const size = Math.max(rect.width, rect.height);
            ripple.style.width = ripple.style.height = size + 'px';
            ripple.style.left = (e.clientX - rect.left - size / 2) + 'px';
            ripple.style.top = (e.clientY - rect.top - size / 2) + 'px';

            btn.style.position = 'relative';
            btn.style.overflow = 'hidden';
            btn.appendChild(ripple);
            setTimeout(() => ripple.remove(), 600);
        });
    }

    // ═══════════════════════════════════════════════════════════════
    //  4. SCROLL REVEAL ANIMATIONS
    // ═══════════════════════════════════════════════════════════════
    function initScrollReveal() {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('revealed');
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.1 });

        // Observe glass cards and stat cards
        document.querySelectorAll('.glass-card, .stat-card-modern').forEach(el => {
            el.classList.add('reveal-on-scroll');
            observer.observe(el);
        });
    }

    // ═══════════════════════════════════════════════════════════════
    //  5. ANIMATED NUMBER COUNTERS
    // ═══════════════════════════════════════════════════════════════
    function initAnimatedCounters() {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    animateValue(entry.target);
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.5 });

        document.querySelectorAll('.stat-value').forEach(el => {
            observer.observe(el);
        });
    }

    function animateValue(el) {
        const text = el.textContent.trim();
        const match = text.match(/([$₹€]?)([\d,]+\.?\d*)(.*)/);
        if (!match) return;

        const prefix = match[1];
        const numStr = match[2].replace(/,/g, '');
        const suffix = match[3];
        const target = parseFloat(numStr);
        if (isNaN(target) || target === 0) return;

        const duration = 800;
        const start = performance.now();
        const isInt = !numStr.includes('.');

        function update(now) {
            const elapsed = now - start;
            const progress = Math.min(elapsed / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
            const current = target * eased;

            if (isInt) {
                el.textContent = prefix + Math.round(current).toLocaleString('en-IN') + suffix;
            } else {
                el.textContent = prefix + current.toFixed(2) + suffix;
            }

            if (progress < 1) requestAnimationFrame(update);
        }

        el.textContent = prefix + '0' + suffix;
        requestAnimationFrame(update);
    }

    // ═══════════════════════════════════════════════════════════════
    //  6. PERSONALIZED GREETING
    // ═══════════════════════════════════════════════════════════════
    function upgradeGreeting() {
        const banner = document.getElementById('smartGreetingBanner');
        if (!banner) return;

        const hour = new Date().getHours();
        let greeting, emoji, suggestion;

        if (hour < 6) { greeting = 'Good Night'; emoji = '🌙'; suggestion = 'Metro opens at 6 AM. Plan your morning commute!'; }
        else if (hour < 12) { greeting = 'Good Morning'; emoji = '☀️'; suggestion = 'Beat the rush! Off-peak hours save you 20%.'; }
        else if (hour < 17) { greeting = 'Good Afternoon'; emoji = '🌤️'; suggestion = 'Perfect time for a trip. Stations are less crowded now.'; }
        else if (hour < 21) { greeting = 'Good Evening'; emoji = '🌆'; suggestion = 'Evening rush detected. Consider booking for the next off-peak window.'; }
        else { greeting = 'Good Night'; emoji = '🌙'; suggestion = 'Last metro at 11 PM. Plan your return trip!'; }

        const username = document.getElementById('navUsername')?.textContent || 'Traveler';

        // Upgrade the existing greeting banner
        const greetingEl = banner.querySelector('h2, h3, .fw-bold');
        if (greetingEl) {
            greetingEl.innerHTML = `<span class="greeting-emoji">${emoji}</span> ${greeting}, ${username}!`;
        }

        // Add suggestion subtitle if not present
        if (!banner.querySelector('.greeting-subtitle')) {
            const sub = document.createElement('p');
            sub.className = 'greeting-subtitle';
            sub.innerHTML = `<i class="fas fa-lightbulb me-1" style="color:#f59e0b;"></i>${suggestion}`;
            const insertTarget = greetingEl || banner.firstChild;
            if (insertTarget && insertTarget.parentNode) {
                insertTarget.parentNode.insertBefore(sub, insertTarget.nextSibling);
            }
        }
    }

    // ═══════════════════════════════════════════════════════════════
    //  7. SMART SUGGESTIONS
    // ═══════════════════════════════════════════════════════════════
    async function loadSmartSuggestions() {
        const dashSection = document.getElementById('dashboard-section');
        if (!dashSection) return;
        if (document.getElementById('smartSuggestionsContainer')) return;

        try {
            // Fetch data
            const [routeRes, passRes, balRes] = await Promise.allSettled([
                fetch('/api/tickets/recent-routes', { credentials: 'include' }).then(r => r.json()),
                fetch('/api/monthly-pass/history', { credentials: 'include' }).then(r => r.json()),
                fetch('/api/user/wallet/balance', { credentials: 'include' }).then(r => r.json())
            ]);

            const suggestions = [];
            const routes = routeRes.status === 'fulfilled' && routeRes.value.success ? routeRes.value.routes : [];
            const passes = passRes.status === 'fulfilled' && passRes.value.success ? passRes.value.passes : [];
            const balance = balRes.status === 'fulfilled' && balRes.value.success ? balRes.value.balance : 0;

            // Suggestion 1: Quick re-book frequent route
            if (routes.length > 0) {
                const r = routes[0];
                const src = r.source.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                const dst = r.destination.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                suggestions.push({
                    icon: '🚇',
                    iconBg: 'rgba(102, 126, 234, 0.1)',
                    title: `Quick Trip: ${src} → ${dst}`,
                    desc: `Your most frequent route (${r.tripCount} trips). Avg fare: ₹${r.avgFare}`,
                    action: `showSection('book-ticket')`,
                    btnText: 'Book Now'
                });
            }

            // Suggestion 2: Low balance warning
            if (balance < 100 && balance >= 0) {
                suggestions.push({
                    icon: '💰',
                    iconBg: 'rgba(245, 158, 11, 0.1)',
                    title: 'Low Wallet Balance',
                    desc: `Your balance is ₹${Number(balance).toFixed(0)}. Recharge to avoid booking issues.`,
                    action: `showSection('wallet')`,
                    btnText: 'Recharge'
                });
            }

            // Suggestion 3: Pass expiring soon
            const expiringPass = passes.find(p => {
                if (p.status !== 'active') return false;
                const days = Math.ceil((new Date(p.expiryDate) - new Date()) / 86400000);
                return days <= 5 && days > 0;
            });

            if (expiringPass) {
                const days = Math.ceil((new Date(expiringPass.expiryDate) - new Date()) / 86400000);
                suggestions.push({
                    icon: '⏰',
                    iconBg: 'rgba(239, 68, 68, 0.1)',
                    title: `Pass Expires in ${days} Day${days > 1 ? 's' : ''}`,
                    desc: `Your ${expiringPass.planType} pass is expiring soon. Renew to keep saving!`,
                    action: `showSection('monthly-pass')`,
                    btnText: 'Renew Pass'
                });
            }

            if (suggestions.length === 0) return;

            // Render
            const container = document.createElement('div');
            container.id = 'smartSuggestionsContainer';
            container.className = 'mb-4';
            container.innerHTML = `
                <div class="d-flex align-items-center gap-2 mb-3">
                    <i class="fas fa-magic" style="color:#667eea;"></i>
                    <span style="font-size:14px;font-weight:800;color:inherit;">Smart Suggestions</span>
                </div>
                ${suggestions.map(s => `
                    <div class="smart-suggestion-card" onclick="${s.action}">
                        <div class="d-flex align-items-center gap-3">
                            <div class="suggestion-icon" style="background:${s.iconBg};">${s.icon}</div>
                            <div style="flex:1;min-width:0;">
                                <div style="font-size:14px;font-weight:700;">${s.title}</div>
                                <div style="font-size:12px;color:#94a3b8;">${s.desc}</div>
                            </div>
                            <button class="suggestion-action-btn" onclick="event.stopPropagation();${s.action}">
                                ${s.btnText} <i class="fas fa-arrow-right ms-1"></i>
                            </button>
                        </div>
                    </div>
                `).join('')}
            `;

            // Insert after weather card or greeting
            const weatherCard = dashSection.querySelector('#weatherAdvisoryCard');
            const greetBanner = dashSection.querySelector('#smartGreetingBanner');
            const insertAfter = weatherCard || greetBanner;
            if (insertAfter && insertAfter.nextSibling) {
                insertAfter.parentNode.insertBefore(container, insertAfter.nextSibling);
            } else {
                dashSection.insertBefore(container, dashSection.children[2]);
            }
        } catch (e) { console.log('Smart suggestions:', e); }
    }

    // ═══════════════════════════════════════════════════════════════
    //  8. ACTIVITY FEED
    // ═══════════════════════════════════════════════════════════════
    async function loadActivityFeed() {
        const dashSection = document.getElementById('dashboard-section');
        if (!dashSection || document.getElementById('activityFeedCard')) return;

        try {
            const res = await fetch('/api/notifications/center', { credentials: 'include' });
            const data = await res.json();
            if (!data.success || !data.notifications?.length) return;

            const activities = data.notifications.slice(0, 5);
            const card = document.createElement('div');
            card.id = 'activityFeedCard';
            card.className = 'glass-card mb-4';
            card.innerHTML = `
                <div class="d-flex align-items-center justify-content-between mb-3">
                    <h6 class="fw-bold mb-0"><i class="fas fa-stream me-2" style="color:#667eea;"></i>Recent Activity</h6>
                    <span style="font-size:11px;color:#94a3b8;font-weight:600;">Last 5</span>
                </div>
                <div class="activity-feed">
                    ${activities.map(a => `
                        <div class="activity-item">
                            <div class="activity-dot" style="background:${a.icon?.includes('💰') || a.icon?.includes('wallet') ? 'rgba(34,197,94,0.1)' : 'rgba(102,126,234,0.1)'};">
                                ${a.icon || '📋'}
                            </div>
                            <div class="activity-text">
                                <div class="activity-title">${a.title || a.message}</div>
                                <div class="activity-time"><i class="fas fa-clock me-1"></i>${a.time || 'Recently'}</div>
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;

            // Insert in dashboard section
            const statsRow = dashSection.querySelector('.row.g-4');
            if (statsRow) {
                statsRow.parentNode.insertBefore(card, statsRow.nextSibling);
            }
        } catch (e) { console.log('Activity feed:', e); }
    }

    // ═══════════════════════════════════════════════════════════════
    //  9. CHATBOT ENHANCEMENTS
    // ═══════════════════════════════════════════════════════════════
    function enhanceChatbot() {
        // Override sendChat to add typing indicator + quick replies
        const origSendChat = window.sendChat;
        if (typeof origSendChat !== 'function') return;

        window.sendChat = function () {
            const input = document.getElementById('chatInput');
            const body = document.getElementById('chatBody');
            if (!input || !body) return origSendChat();

            const msg = input.value.trim();
            if (!msg) return;

            // Add user message
            const userEl = document.createElement('div');
            userEl.className = 'chat-msg msg-user';
            userEl.textContent = msg;
            body.appendChild(userEl);
            input.value = '';

            // Show typing indicator
            const typing = document.createElement('div');
            typing.className = 'chat-typing-indicator';
            typing.innerHTML = '<div class="chat-typing-dot"></div><div class="chat-typing-dot"></div><div class="chat-typing-dot"></div>';
            body.appendChild(typing);
            body.scrollTop = body.scrollHeight;

            // Simulate bot response with delay
            setTimeout(() => {
                typing.remove();
                origSendChat.call(window);

                // Add quick replies after bot responds
                setTimeout(() => {
                    if (!body.querySelector('.chat-quick-replies:last-child')) {
                        const replies = document.createElement('div');
                        replies.className = 'chat-quick-replies';
                        replies.innerHTML = `
                            <button class="chat-quick-btn" onclick="document.getElementById('chatInput').value='Check fare';sendChat()">💰 Check Fare</button>
                            <button class="chat-quick-btn" onclick="document.getElementById('chatInput').value='Book ticket';sendChat()">🎫 Book Ticket</button>
                            <button class="chat-quick-btn" onclick="document.getElementById('chatInput').value='Station info';sendChat()">📍 Station Info</button>
                        `;
                        body.appendChild(replies);
                        body.scrollTop = body.scrollHeight;
                    }
                }, 300);
            }, 800 + Math.random() * 700);
        };
    }

    // ═══════════════════════════════════════════════════════════════
    //  10. COACH SELECTOR VISUAL
    // ═══════════════════════════════════════════════════════════════
    function enhanceCoachSelector() {
        const coachSelect = document.getElementById('coachPreference');
        if (!coachSelect || document.getElementById('coachVisualSelector')) return;

        const coaches = [
            { value: 'general', icon: '🚃', name: 'General', desc: 'Standard coach', color: '#667eea' },
            { value: 'ladies', icon: '👩', name: 'Ladies', desc: 'Women only', color: '#f093fb' },
            { value: 'senior', icon: '🧓', name: 'Senior', desc: 'Priority seating', color: '#f59e0b' },
            { value: 'wheelchair', icon: '♿', name: 'Accessible', desc: 'Wheelchair access', color: '#4facfe' }
        ];

        const container = document.createElement('div');
        container.id = 'coachVisualSelector';
        container.className = 'coach-selector';
        container.innerHTML = coaches.map(c => `
            <div class="coach-option ${c.value === coachSelect.value ? 'selected' : ''}" 
                 data-coach="${c.value}" 
                 onclick="selectCoach('${c.value}')">
                <span class="coach-icon">${c.icon}</span>
                <div class="coach-name">${c.name}</div>
                <div class="coach-desc">${c.desc}</div>
            </div>
        `).join('');

        coachSelect.style.display = 'none';
        coachSelect.parentNode.insertBefore(container, coachSelect.nextSibling);

        window.selectCoach = function (val) {
            coachSelect.value = val;
            document.querySelectorAll('.coach-option').forEach(o => o.classList.remove('selected'));
            document.querySelector(`.coach-option[data-coach="${val}"]`)?.classList.add('selected');
        };
    }

    // ═══════════════════════════════════════════════════════════════
    //  11. QUICK RECHARGE CHIPS
    // ═══════════════════════════════════════════════════════════════
    function enhanceWalletChips() {
        const rechargeInput = document.getElementById('rechargeAmount');
        if (!rechargeInput || document.getElementById('rechargeChipsContainer')) return;

        const amounts = [100, 200, 500, 1000, 2000];
        const container = document.createElement('div');
        container.id = 'rechargeChipsContainer';
        container.className = 'recharge-chips';
        container.innerHTML = amounts.map(a => `
            <button class="recharge-chip" onclick="selectRechargeAmount(${a}, this)">₹${a}</button>
        `).join('');

        rechargeInput.parentNode.insertBefore(container, rechargeInput);

        window.selectRechargeAmount = function (amount, btn) {
            rechargeInput.value = amount;
            document.querySelectorAll('.recharge-chip').forEach(c => c.classList.remove('selected'));
            btn.classList.add('selected');
            // Trigger input event for any listeners
            rechargeInput.dispatchEvent(new Event('input', { bubbles: true }));
        };

        // Clear chip selection when user manually types
        rechargeInput.addEventListener('input', function () {
            const val = parseInt(this.value);
            document.querySelectorAll('.recharge-chip').forEach(c => {
                c.classList.toggle('selected', parseInt(c.textContent.replace('₹', '')) === val);
            });
        });
    }

    // ═══════════════════════════════════════════════════════════════
    //  12. CROWD LEVEL INDICATORS
    // ═══════════════════════════════════════════════════════════════
    function initCrowdIndicators() {
        // Inject crowd indicator after station select in booking
        const sourceSelect = document.getElementById('source');
        const destSelect = document.getElementById('destination');
        if (!sourceSelect || !destSelect) return;

        function createCrowdIndicator(station, containerId) {
            if (!station) return;
            let existing = document.getElementById(containerId);
            if (existing) existing.remove();

            const hour = new Date().getHours();
            const isPeak = (hour >= 8 && hour < 11) || (hour >= 17 && hour < 19);
            const level = isPeak ? (Math.random() > 0.4 ? 'high' : 'medium') : (Math.random() > 0.6 ? 'medium' : 'low');
            const labels = { low: 'Low Crowd', medium: 'Moderate', high: 'Crowded' };
            const barHeights = { low: [8, 12, 6, 10, 5], medium: [12, 16, 14, 10, 15], high: [16, 20, 18, 14, 19] };

            const indicator = document.createElement('div');
            indicator.id = containerId;
            indicator.className = 'crowd-indicator';
            indicator.innerHTML = `
                <div class="crowd-bars">
                    ${barHeights[level].map(h => `<div class="crowd-bar active ${level}" style="height:${h}px;"></div>`).join('')}
                </div>
                <span class="crowd-label ${level}">${labels[level]}</span>
                <span style="font-size:10px;color:#94a3b8;margin-left:auto;">${isPeak ? '⚡ Peak Hour' : '✅ Off-Peak'}</span>
            `;

            const parent = document.getElementById(containerId.includes('source') ? 'source' : 'destination');
            if (parent && parent.closest('.mb-3, .mb-4, .form-group-modern, .col-12')) {
                parent.closest('.mb-3, .mb-4, .form-group-modern, .col-12').appendChild(indicator);
            }
        }

        sourceSelect.addEventListener('change', () => createCrowdIndicator(sourceSelect.value, 'crowdSource'));
        destSelect.addEventListener('change', () => createCrowdIndicator(destSelect.value, 'crowdDest'));
    }

    // ═══════════════════════════════════════════════════════════════
    //  13. BOOKING CELEBRATION (hooks into booking success)
    // ═══════════════════════════════════════════════════════════════
    // Override the booking success handler if it exists
    const origBookTicket = window.bookTicket;
    if (typeof origBookTicket === 'function') {
        window.bookTicket = async function () {
            const result = await origBookTicket.apply(this, arguments);
            // If booking was successful, the success toast/alert would have been shown
            // We add confetti celebration
            return result;
        };
    }

    // Hook into successful booking responses globally
    const origFetch = window.fetch;
    window.fetch = function (...args) {
        return origFetch.apply(this, args).then(response => {
            const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
            if (url.includes('/api/tickets/book') && response.ok) {
                response.clone().json().then(data => {
                    if (data.success) {
                        setTimeout(() => {
                            if (typeof launchConfetti === 'function') launchConfetti();
                        }, 500);
                    }
                }).catch(() => {});
            }
            return response;
        });
    };

    // ═══════════════════════════════════════════════════════════════
    //  14. SECTION TRANSITION ANIMATION
    // ═══════════════════════════════════════════════════════════════
    const origShowSection = window.showSection;
    if (typeof origShowSection === 'function') {
        const _enhancedShow = window.showSection; // capture current (may be wrapped by improvements.js)
        window.showSection = function (section) {
            _enhancedShow(section);

            // Add entrance animation
            const el = document.getElementById(section + '-section');
            if (el && el.style.display !== 'none') {
                el.classList.remove('section-enter');
                void el.offsetWidth; // force reflow
                el.classList.add('section-enter');
            }
        };
    }

})();

// ═══════════════════════════════════════════════════════════════════════
// NEW FEATURE JS — Live Trains, Journey Planner, Achievements,
//                  Commute Insights, Station Info Panel
// ═══════════════════════════════════════════════════════════════════════

// ── LIVE TRAINS ──────────────────────────────────────────────────────────
let _trainInterval = null;
async function loadLiveTrains() {
    try {
        const res = await fetch('/api/live-trains', { credentials: 'include' });
        const data = await res.json();
        if (!data.success) return;
        const blue = data.trains.filter(t => t.line === 'Blue');
        const red = data.trains.filter(t => t.line === 'Red');
        renderTrainList('blueLineTrains', blue);
        renderTrainList('redLineTrains', red);
        const ts = document.getElementById('liveTrainTime');
        if (ts) ts.innerHTML = `<i class="fas fa-circle me-1" style="font-size:6px;animation:pulse 1.5s infinite;"></i> LIVE · ${data.timestamp}`;
    } catch (e) { console.log('Live trains:', e); }
}
function renderTrainList(containerId, trains) {
    const el = document.getElementById(containerId);
    if (!el) return;
    if (!trains.length) { el.innerHTML = '<div style="text-align:center;padding:20px;color:#94a3b8;">No active trains</div>'; return; }
    el.innerHTML = trains.map(t => {
        const crowdCls = t.occupancy.toLowerCase().replace(' ', '-');
        const pct = Math.round((t.stationIndex / (t.totalStations - 1)) * 100);
        return `<div class="train-card">
            <div class="train-id-badge" style="background:${t.lineColor};">${t.trainId}</div>
            <div class="train-info">
                <div class="train-station">${t.currentStation.replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase())}</div>
                <div class="train-next"><i class="fas fa-arrow-right me-1"></i>Next: ${t.nextStation.replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase())} · ${t.eta} min</div>
                <div style="height:4px;background:rgba(0,0,0,0.06);border-radius:2px;margin-top:6px;overflow:hidden;">
                    <div style="height:100%;width:${pct}%;background:${t.lineColor};border-radius:2px;transition:width 1s;"></div>
                </div>
            </div>
            <div class="train-meta">
                <span class="crowd-pill ${crowdCls}">${t.occupancy}</span>
                <div class="train-live-dot" style="background:${t.lineColor};"></div>
            </div>
        </div>`;
    }).join('');
}
function startTrainPolling() {
    loadLiveTrains();
    if (_trainInterval) clearInterval(_trainInterval);
    _trainInterval = setInterval(loadLiveTrains, 8000);
}
function stopTrainPolling() { if (_trainInterval) { clearInterval(_trainInterval); _trainInterval = null; } }

// ── JOURNEY PLANNER ──────────────────────────────────────────────────────
function initJourneyPlannerDropdowns() {
    const allStations = [
        'thaltej_gam','thaltej','doordarshan_kendra','gurukul_road','gujarat_university',
        'commerce_six_road','stadium','old_high_court','shahpur','gheekanta',
        'kalupur_railway_station','kankaria_east','apparel_park','amraiwadi',
        'rabari_colony','vastral','nirant_cross_road','vastral_gam',
        'apmc','jivraj','rajiv_nagar','shreyas','paldi','gandhigram',
        'usmanpura','vijay_nagar','vadaj','ranip','sabarmati_railway_station','aec',
        'sabarmati','motera_stadium'
    ];
    const unique = [...new Set(allStations)].sort();
    ['jpSource','jpDest'].forEach(id => {
        const sel = document.getElementById(id);
        if (!sel || sel.options.length > 1) return;
        sel.innerHTML = '<option value="">— Select Station —</option>' +
            unique.map(s => `<option value="${s}">${s.replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase())}</option>`).join('');
    });
}

async function planJourney() {
    const src = document.getElementById('jpSource')?.value;
    const dst = document.getElementById('jpDest')?.value;
    const box = document.getElementById('jpResults');
    if (!src || !dst) { if (box) box.innerHTML = '<div style="text-align:center;padding:40px;color:#ef4444;font-weight:600;"><i class="fas fa-exclamation-circle me-2"></i>Please select both stations</div>'; return; }
    box.innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8;"><i class="fas fa-spinner fa-spin me-2"></i>Planning route...</div>';
    try {
        const res = await fetch('/api/journey/plan-route', { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include', body: JSON.stringify({ source: src, destination: dst }) });
        const data = await res.json();
        if (!data.success || !data.journey) { box.innerHTML = `<div style="text-align:center;padding:40px;color:#ef4444;font-weight:600;">${data.error || 'Route not found. These stations may not be connected.'}</div>`; return; }
        const j = data.journey;
        if (!j.segments || !j.segments.length) { box.innerHTML = '<div style="text-align:center;padding:40px;color:#ef4444;font-weight:600;">No route available between these stations</div>'; return; }
        const fmt = s => s.replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase());
        let html = '<h6 class="fw-bold mb-3"><i class="fas fa-map-signs me-2" style="color:#667eea;"></i>Your Route</h6>';
        j.segments.forEach(seg => {
            const icon = seg.line === 'Interchange' ? 'fa-exchange-alt' : 'fa-subway';
            html += `<div class="jp-segment">
                <div class="jp-dot" style="background:${seg.lineColor};"><i class="fas ${icon}"></i></div>
                <div class="jp-segment-info">
                    <div class="jp-line-label" style="color:${seg.lineColor};">${seg.line} Line</div>
                    <div class="jp-stations">${fmt(seg.from)} → ${fmt(seg.to)}</div>
                    <div class="jp-meta">${seg.line === 'Interchange' ? 'Walk to platform · ~5 min' : `${seg.stations} stations · ~${seg.time} min`}</div>
                </div>
            </div>`;
        });
        html += `<div class="jp-summary">
            <div class="jp-summary-item"><div class="jp-summary-value">${j.totalTime}<span style="font-size:12px;"> min</span></div><div class="jp-summary-label">Total Time</div></div>
            <div class="jp-summary-item"><div class="jp-summary-value">${j.totalStations}</div><div class="jp-summary-label">Stations</div></div>
            <div class="jp-summary-item"><div class="jp-summary-value">₹${j.fare}</div><div class="jp-summary-label">Fare${j.isPeak ? ' (Peak)' : ''}</div></div>
            <div class="jp-summary-item"><div class="jp-summary-value">${j.distance}<span style="font-size:12px;"> km</span></div><div class="jp-summary-label">Distance</div></div>
        </div>`;
        if (j.interchange) html += '<div style="margin-top:14px;padding:10px 14px;border-radius:12px;background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.15);font-size:12px;font-weight:600;color:#f59e0b;"><i class="fas fa-info-circle me-2"></i>Interchange at Old High Court — allow 5 min for platform transfer</div>';
        html += `<button onclick="showSection('book-ticket')" class="btn btn-gradient w-100 mt-3" style="border-radius:14px;"><i class="fas fa-ticket-alt me-2"></i>Book This Trip</button>`;
        box.innerHTML = html;
    } catch (e) { box.innerHTML = `<div style="text-align:center;padding:40px;color:#ef4444;">${e.message}</div>`; }
}

// ── ACHIEVEMENTS ─────────────────────────────────────────────────────────
async function loadAchievements() {
    try {
        const res = await fetch('/api/achievements', { credentials: 'include' });
        const data = await res.json();
        const grid = document.getElementById('achievementsGrid');
        const counter = document.getElementById('achievementCounter');
        if (!grid) return;
        if (!data.achievements?.length) { grid.innerHTML = '<div style="text-align:center;padding:60px;color:#94a3b8;">No achievements data</div>'; return; }
        if (counter) counter.textContent = `${data.earned} / ${data.total} Unlocked`;
        grid.innerHTML = data.achievements.map(a => {
            const pct = Math.round((a.current / a.target) * 100);
            return `<div class="col-md-4 col-6">
                <div class="achievement-card ${a.earned ? 'earned' : 'locked'}">
                    ${a.earned ? '<div class="achievement-earned-badge">✓ EARNED</div>' : ''}
                    <span class="achievement-emoji">${a.icon}</span>
                    <div class="achievement-name">${a.name}</div>
                    <div class="achievement-desc">${a.desc}</div>
                    <div class="achievement-progress"><div class="achievement-progress-fill" style="width:${pct}%;"></div></div>
                    <div class="achievement-progress-text">${a.current} / ${a.target}</div>
                </div>
            </div>`;
        }).join('');
    } catch (e) { console.log('Achievements:', e); }
}

// ── COMMUTE INSIGHTS ─────────────────────────────────────────────────────
async function loadCommuteInsights() {
    try {
        const res = await fetch('/api/user/commute-insights', { credentials: 'include' });
        const data = await res.json();
        const grid = document.getElementById('insightsGrid');
        if (!grid || !data.insights) return;
        const i = data.insights;
        const changeCls = i.weekChange > 0 ? 'up' : i.weekChange < 0 ? 'down' : 'neutral';
        const changeIcon = i.weekChange > 0 ? 'fa-arrow-up' : i.weekChange < 0 ? 'fa-arrow-down' : 'fa-minus';
        const days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
        const maxDay = Math.max(...days.map(d => i.dayDistribution?.[d] || 0), 1);
        grid.innerHTML = `
            <div class="col-md-4 col-6"><div class="insight-card">
                <div class="insight-icon" style="background:rgba(102,126,234,0.1);color:#667eea;"><i class="fas fa-subway"></i></div>
                <div class="insight-value">${i.weeklyTrips}</div><div class="insight-label">Trips This Week</div>
                <div class="insight-change ${changeCls}"><i class="fas ${changeIcon}"></i> ${Math.abs(i.weekChange)}% vs last week</div>
            </div></div>
            <div class="col-md-4 col-6"><div class="insight-card">
                <div class="insight-icon" style="background:rgba(34,197,94,0.1);color:#22c55e;"><i class="fas fa-leaf"></i></div>
                <div class="insight-value">${i.co2Saved}<span style="font-size:14px;"> kg</span></div><div class="insight-label">CO₂ Saved</div>
                <div class="insight-change up"><i class="fas fa-tree"></i> ${i.totalKm} km by metro</div>
            </div></div>
            <div class="col-md-4 col-6"><div class="insight-card">
                <div class="insight-icon" style="background:rgba(245,158,11,0.1);color:#f59e0b;"><i class="fas fa-fire"></i></div>
                <div class="insight-value">${i.totalTrips}</div><div class="insight-label">Total Trips</div>
                <div class="insight-change neutral"><i class="fas fa-star"></i> Busiest: ${i.busiestDay}</div>
            </div></div>
            <div class="col-md-4 col-6"><div class="insight-card">
                <div class="insight-icon" style="background:rgba(239,68,68,0.1);color:#ef4444;"><i class="fas fa-clock"></i></div>
                <div class="insight-value">${i.peakTrips}<span style="font-size:14px;"> / ${i.offpeakTrips}</span></div><div class="insight-label">Peak / Off-Peak</div>
                <div style="height:6px;background:rgba(0,0,0,0.06);border-radius:3px;margin-top:8px;overflow:hidden;display:flex;">
                    <div style="width:${i.totalTrips ? (i.peakTrips/i.totalTrips*100) : 50}%;background:#ef4444;"></div>
                    <div style="flex:1;background:#22c55e;"></div>
                </div>
            </div></div>
            <div class="col-md-4 col-6"><div class="insight-card">
                <div class="insight-icon" style="background:rgba(118,75,162,0.1);color:#764ba2;"><i class="fas fa-piggy-bank"></i></div>
                <div class="insight-value">₹${i.moneySaved}</div><div class="insight-label">Pass Savings</div>
                <div class="insight-change ${i.moneySaved > 0 ? 'up' : 'neutral'}"><i class="fas fa-${i.moneySaved > 0 ? 'check' : 'info-circle'}"></i> From monthly pass</div>
            </div></div>
            <div class="col-md-4 col-6"><div class="insight-card">
                <div class="insight-icon" style="background:rgba(79,172,254,0.1);color:#4facfe;"><i class="fas fa-calendar-week"></i></div>
                <div class="insight-label" style="margin-bottom:8px;">Weekly Activity</div>
                <div class="day-heatmap">
                    ${days.map(d => {
                        const cnt = i.dayDistribution?.[d] || 0;
                        const intensity = cnt / maxDay;
                        const bg = cnt === 0 ? 'rgba(0,0,0,0.04)' : `rgba(102,126,234,${0.15 + intensity * 0.7})`;
                        const color = cnt === 0 ? '#cbd5e1' : (intensity > 0.5 ? 'white' : '#667eea');
                        return `<div class="day-heat-cell" style="background:${bg};color:${color};" title="${d}: ${cnt} trips">${d[0]}</div>`;
                    }).join('')}
                </div>
            </div></div>`;
    } catch (e) { console.log('Insights:', e); }
}

// ── STATION INFO PANEL ───────────────────────────────────────────────────
function initStationInfoPanel() {
    if (document.getElementById('stationInfoOverlay')) return;
    const overlay = document.createElement('div');
    overlay.id = 'stationInfoOverlay';
    overlay.className = 'station-info-overlay';
    overlay.innerHTML = `<div class="station-info-panel" id="stationInfoPanel">
        <div class="station-info-header"><div class="station-info-handle"></div>
            <h5 id="stationInfoName" class="mb-1 fw-bold">Station Name</h5>
            <div id="stationInfoLine" style="font-size:12px;opacity:0.8;"></div>
        </div>
        <div class="station-info-body" id="stationInfoBody">Loading...</div>
    </div>`;
    overlay.addEventListener('click', e => { if (e.target === overlay) closeStationInfo(); });
    document.body.appendChild(overlay);
}
async function openStationInfo(stationName) {
    initStationInfoPanel();
    const overlay = document.getElementById('stationInfoOverlay');
    overlay.classList.add('active');
    document.getElementById('stationInfoBody').innerHTML = '<div style="text-align:center;padding:30px;color:#94a3b8;"><i class="fas fa-spinner fa-spin me-2"></i>Loading...</div>';
    try {
        const res = await fetch(`/api/station/info/${stationName}`, { credentials: 'include' });
        const data = await res.json();
        if (!data.success) return;
        const s = data.station;
        document.getElementById('stationInfoName').textContent = s.displayName;
        document.getElementById('stationInfoLine').innerHTML = `<i class="fas fa-subway me-1"></i>${s.line} Line${s.isInterchange ? ' · <span style="color:#f59e0b;">⚡ Interchange</span>' : ''}`;
        const crowdColor = s.crowd === 'Low' ? '#22c55e' : s.crowd === 'Moderate' ? '#f59e0b' : '#ef4444';
        const amenityIcons = { 'Wheelchair Access': 'fa-wheelchair', 'Restrooms': 'fa-restroom', 'Parking': 'fa-parking', 'Food Court': 'fa-utensils', 'ATM': 'fa-money-bill-wave' };
        document.getElementById('stationInfoBody').innerHTML = `
            <div style="margin-bottom:18px;">
                <div style="font-size:12px;font-weight:700;text-transform:uppercase;color:#94a3b8;margin-bottom:6px;">Crowd Level</div>
                <div style="display:flex;align-items:center;gap:10px;">
                    <span style="font-size:20px;font-weight:900;color:${crowdColor};">${s.crowd}</span>
                    <span style="font-size:12px;color:#94a3b8;">${s.crowdPct}% capacity</span>
                </div>
                <div class="station-crowd-meter"><div class="station-crowd-fill" style="width:${s.crowdPct}%;background:${crowdColor};"></div></div>
            </div>
            <div style="margin-bottom:18px;">
                <div style="font-size:12px;font-weight:700;text-transform:uppercase;color:#94a3b8;margin-bottom:8px;">Next Trains</div>
                ${s.nextTrains.map(t => `<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 12px;background:rgba(0,0,0,0.02);border-radius:10px;margin-bottom:6px;">
                    <span style="font-size:13px;font-weight:600;">${t.direction}</span>
                    <span style="background:${t.line==='Blue'?'rgba(79,172,254,0.1)':'rgba(239,68,68,0.1)'};color:${t.line==='Blue'?'#4facfe':'#ef4444'};font-size:12px;font-weight:700;padding:3px 10px;border-radius:8px;">${t.eta} min</span>
                </div>`).join('')}
            </div>
            <div style="margin-bottom:18px;">
                <div style="font-size:12px;font-weight:700;text-transform:uppercase;color:#94a3b8;margin-bottom:8px;">Amenities</div>
                <div class="station-amenity-grid">${s.amenities.map(a => `<span class="station-amenity"><i class="fas ${amenityIcons[a]||'fa-check'} me-1"></i>${a}</span>`).join('')}</div>
            </div>
            ${s.popularDestinations?.length ? `<div>
                <div style="font-size:12px;font-weight:700;text-transform:uppercase;color:#94a3b8;margin-bottom:8px;">Popular From Here</div>
                ${s.popularDestinations.map(p => `<div style="display:flex;align-items:center;justify-content:space-between;padding:6px 0;font-size:13px;">
                    <span>${p.station.replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase())}</span>
                    <span style="color:#94a3b8;font-size:11px;">${p.trips} trips</span>
                </div>`).join('')}
            </div>` : ''}
            <button onclick="closeStationInfo();showSection('book-ticket')" class="btn btn-gradient w-100 mt-3" style="border-radius:14px;font-size:13px;padding:12px;">
                <i class="fas fa-ticket-alt me-2"></i>Book From ${s.displayName}
            </button>`;
    } catch (e) { document.getElementById('stationInfoBody').innerHTML = `<div style="color:#ef4444;">${e.message}</div>`; }
}
function closeStationInfo() { document.getElementById('stationInfoOverlay')?.classList.remove('active'); }

// ── HOOK: detect section visibility via MutationObserver ─────────────────
// This is more robust than wrapping showSection (which gets wrapped many times)
(function() {
    const sectionHandlers = {
        'live-trains-section': () => startTrainPolling(),
        'journey-planner-section': () => initJourneyPlannerDropdowns(),
        'achievements-section': () => loadAchievements(),
        'commute-insights-section': () => loadCommuteInsights()
    };
    const observer = new MutationObserver(mutations => {
        mutations.forEach(m => {
            if (m.type === 'attributes' && m.attributeName === 'style') {
                const el = m.target;
                if (el.id && sectionHandlers[el.id]) {
                    if (el.style.display !== 'none') {
                        sectionHandlers[el.id]();
                    } else if (el.id === 'live-trains-section') {
                        stopTrainPolling();
                    }
                }
            }
        });
    });
    // Observe all content sections
    document.addEventListener('DOMContentLoaded', () => {
        setTimeout(() => {
            Object.keys(sectionHandlers).forEach(id => {
                const el = document.getElementById(id);
                if (el) observer.observe(el, { attributes: true, attributeFilter: ['style'] });
            });
        }, 500);
    });
    // Fallback: also observe on window load
    window.addEventListener('load', () => {
        setTimeout(() => {
            Object.keys(sectionHandlers).forEach(id => {
                const el = document.getElementById(id);
                if (el) observer.observe(el, { attributes: true, attributeFilter: ['style'] });
            });
        }, 2000);
    });
})();

// ═══════════════════════════════════════════════════════════════════════
// NEW FEATURE JS — Fare Compare, Trip Calendar, Nearby Places,
//                  Favorite Routes, Emergency SOS
// ═══════════════════════════════════════════════════════════════════════

const _ALL_STATIONS = [
    'thaltej_gam','thaltej','doordarshan_kendra','gurukul_road','gujarat_university',
    'commerce_six_road','stadium','old_high_court','shahpur','gheekanta',
    'kalupur_railway_station','kankaria_east','apparel_park','amraiwadi',
    'rabari_colony','vastral','nirant_cross_road','vastral_gam',
    'apmc','jivraj','rajiv_nagar','shreyas','paldi','gandhigram',
    'usmanpura','vijay_nagar','vadaj','ranip','sabarmati_railway_station','aec',
    'sabarmati','motera_stadium'
];
function _populateDropdowns(ids) {
    const unique = [...new Set(_ALL_STATIONS)].sort();
    ids.forEach(id => {
        const sel = document.getElementById(id);
        if (!sel || sel.options.length > 1) return;
        sel.innerHTML = '<option value="">— Select —</option>' +
            unique.map(s => `<option value="${s}">${s.replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase())}</option>`).join('');
    });
}

// ── FARE COMPARE ─────────────────────────────────────────────────────────
function initFareCompare() { _populateDropdowns(['fcSource','fcDest']); }

async function compareFares() {
    const src = document.getElementById('fcSource')?.value;
    const dst = document.getElementById('fcDest')?.value;
    const box = document.getElementById('fcResults');
    if (!src || !dst) { box.innerHTML = '<div style="text-align:center;padding:40px;color:#ef4444;font-weight:600;"><i class="fas fa-exclamation-circle me-2"></i>Select both stations</div>'; return; }
    box.innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8;"><i class="fas fa-spinner fa-spin me-2"></i>Comparing fares...</div>';
    try {
        const res = await fetch('/api/fare/compare-all', { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include', body: JSON.stringify({ source: src, destination: dst }) });
        const data = await res.json();
        if (!data.success) { box.innerHTML = `<div style="text-align:center;padding:40px;color:#ef4444;">${data.error}</div>`; return; }
        let html = '';
        if (data.metroSavings > 0) {
            html += `<div class="fc-savings-banner">
                <div><div class="fc-savings-value">₹${data.metroSavings}</div><div class="fc-savings-label">saved vs cab</div></div>
                <div style="flex:1;font-size:12px;color:#94a3b8;"><i class="fas fa-leaf me-1" style="color:#22c55e;"></i>Metro saves money AND the planet. Distance: ${data.distance} km</div>
            </div>`;
        }
        html += '<div style="display:flex;flex-direction:column;gap:12px;">';
        data.comparison.forEach(m => {
            html += `<div class="fc-mode-card ${m.recommended ? 'recommended' : ''}">
                ${m.tag ? `<div class="fc-tag" style="background:${m.recommended ? 'rgba(102,126,234,0.15);color:#667eea' : 'rgba(148,163,184,0.1);color:#94a3b8'}">${m.tag}</div>` : ''}
                <div class="fc-mode-icon" style="background:${m.color};"><i class="fas ${m.icon}"></i></div>
                <div class="fc-mode-info">
                    <div class="fc-mode-name">${m.mode}</div>
                    <div class="fc-mode-meta"><i class="fas fa-smog me-1"></i>${m.co2}g CO₂</div>
                </div>
                <div class="fc-mode-fare">
                    <div class="fc-fare-value" style="color:${m.color};">₹${m.fare}</div>
                    <div class="fc-fare-time"><i class="fas fa-clock me-1"></i>${m.time} min</div>
                </div>
            </div>`;
        });
        html += '</div>';
        box.innerHTML = html;
    } catch (e) { box.innerHTML = `<div style="color:#ef4444;">${e.message}</div>`; }
}

// ── TRIP CALENDAR ────────────────────────────────────────────────────────
async function loadTripCalendar() {
    try {
        const res = await fetch('/api/user/trip-calendar', { credentials: 'include' });
        const data = await res.json();
        const statsEl = document.getElementById('calendarStats');
        const heatEl = document.getElementById('calendarHeatmap');
        const streakEl = document.getElementById('calendarStreak');
        if (!data.success || !data.calendar) return;

        const stats = data.stats || {};
        if (streakEl) streakEl.innerHTML = `<i class="fas fa-fire me-1"></i>${stats.currentStreak || 0} day streak`;
        if (statsEl) statsEl.innerHTML = `
            <div class="col-3"><div class="cal-stat-card"><div class="cal-stat-value" style="color:#667eea;">${stats.activeDays || 0}</div><div class="cal-stat-label">Active Days</div></div></div>
            <div class="col-3"><div class="cal-stat-card"><div class="cal-stat-value" style="color:#22c55e;">${stats.currentStreak || 0}</div><div class="cal-stat-label">Current Streak</div></div></div>
            <div class="col-3"><div class="cal-stat-card"><div class="cal-stat-value" style="color:#f59e0b;">${stats.maxTripsInDay || 0}</div><div class="cal-stat-label">Max In Day</div></div></div>
            <div class="col-3"><div class="cal-stat-card"><div class="cal-stat-value" style="color:#ef4444;">${stats.totalDays || 180}</div><div class="cal-stat-label">Days Tracked</div></div></div>`;

        if (!heatEl || !data.calendar.length) return;
        const cal = data.calendar;
        const maxTrips = Math.max(...cal.map(c => c.trips), 1);
        const colors = ['rgba(0,0,0,0.04)', 'rgba(34,197,94,0.25)', 'rgba(34,197,94,0.45)', 'rgba(34,197,94,0.65)', 'rgba(34,197,94,0.9)'];
        function getColor(trips) {
            if (trips === 0) return colors[0];
            const idx = Math.min(Math.ceil((trips / maxTrips) * 4), 4);
            return colors[idx];
        }
        // Build weeks (columns)
        const weeks = [];
        let currentWeek = [];
        const firstDay = new Date(cal[0].date).getDay();
        for (let i = 0; i < firstDay; i++) currentWeek.push(null);
        cal.forEach(c => {
            currentWeek.push(c);
            if (currentWeek.length === 7) { weeks.push(currentWeek); currentWeek = []; }
        });
        if (currentWeek.length) { while (currentWeek.length < 7) currentWeek.push(null); weeks.push(currentWeek); }

        const dayLabels = ['S','M','T','W','T','F','S'];
        let grid = '<div style="display:flex;gap:3px;align-items:flex-start;">';
        grid += '<div style="display:flex;flex-direction:column;gap:3px;padding-top:0;">';
        dayLabels.forEach(d => grid += `<div style="height:16px;width:20px;font-size:9px;color:#94a3b8;display:flex;align-items:center;justify-content:flex-end;padding-right:4px;">${d}</div>`);
        grid += '</div>';
        weeks.forEach(week => {
            grid += '<div style="display:flex;flex-direction:column;gap:3px;">';
            week.forEach(day => {
                if (!day) { grid += '<div style="width:16px;height:16px;"></div>'; return; }
                grid += `<div class="cal-cell" style="background:${getColor(day.trips)};" title="${day.date}: ${day.trips} trips, ₹${day.fare}" data-trips="${day.trips}"></div>`;
            });
            grid += '</div>';
        });
        grid += '</div>';
        grid += `<div class="cal-legend"><span>Less</span>
            ${colors.map(c => `<div class="cal-legend-cell" style="background:${c};"></div>`).join('')}
            <span>More</span></div>`;
        heatEl.innerHTML = grid;
    } catch (e) { console.log('Trip calendar:', e); }
}

// ── NEARBY PLACES ────────────────────────────────────────────────────────
function initNearbyPlaces() { _populateDropdowns(['nearbyStationSelect']); }

async function loadNearbyPlaces() {
    const station = document.getElementById('nearbyStationSelect')?.value;
    const grid = document.getElementById('nearbyGrid');
    if (!station || !grid) return;
    grid.innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8;width:100%;"><i class="fas fa-spinner fa-spin me-2"></i>Loading...</div>';
    try {
        const res = await fetch(`/api/station/nearby/${station}`, { credentials: 'include' });
        const data = await res.json();
        if (!data.success || !data.places?.length) { grid.innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8;width:100%;">No nearby places found</div>'; return; }
        const typeColors = { Landmark: '#667eea', Food: '#f59e0b', Park: '#22c55e', Shopping: '#ec4899', Transit: '#3b82f6', Heritage: '#8b5cf6', Sports: '#ef4444', Education: '#4facfe', Attraction: '#f97316', Entertainment: '#a855f7', Museum: '#6366f1', Recreation: '#14b8a6', Services: '#94a3b8' };
        grid.innerHTML = `<div class="col-12"><h6 class="fw-bold mb-0"><i class="fas fa-map-marker-alt me-2" style="color:#667eea;"></i>Near ${data.station}</h6></div>` +
            data.places.map(p => {
                const color = typeColors[p.type] || '#667eea';
                return `<div class="col-md-4 col-6">
                    <div class="nearby-card">
                        <div class="nearby-icon" style="background:${color}15;color:${color};"><i class="fas ${p.icon}"></i></div>
                        <div class="nearby-name">${p.name}</div>
                        <div class="nearby-type" style="color:${color};">${p.type}</div>
                        <div class="nearby-dist"><i class="fas fa-walking"></i>${p.dist}</div>
                    </div>
                </div>`;
            }).join('');
    } catch (e) { grid.innerHTML = `<div style="color:#ef4444;">${e.message}</div>`; }
}

// ── FAVORITE ROUTES ──────────────────────────────────────────────────────
async function loadFavoriteRoutes() {
    const grid = document.getElementById('favRoutesGrid');
    if (!grid) return;
    try {
        const res = await fetch('/api/user/favorite-routes', { credentials: 'include' });
        const data = await res.json();
        if (!data.routes?.length) { grid.innerHTML = '<div style="text-align:center;padding:60px;color:#94a3b8;width:100%;"><i class="fas fa-heart" style="font-size:48px;opacity:0.2;display:block;margin-bottom:16px;"></i><div style="font-weight:700;">No favorite routes yet</div><div style="font-size:12px;">Book some trips and your frequent routes will appear here</div></div>'; return; }
        grid.innerHTML = data.routes.map((r, i) => `
            <div class="col-lg-3 col-md-4 col-6">
                <div class="fav-route-card">
                    <div class="fav-route-header">
                        <div class="fav-route-num">${i + 1}</div>
                        <div class="fav-route-path">${r.sourceDisplay}<span class="fav-route-arrow">→</span>${r.destDisplay}</div>
                    </div>
                    <div class="fav-route-stats">
                        <div class="fav-stat"><div class="fav-stat-value">${r.tripCount}</div><div class="fav-stat-label">Trips</div></div>
                        <div class="fav-stat"><div class="fav-stat-value">₹${r.avgFare}</div><div class="fav-stat-label">Avg Fare</div></div>
                        <div class="fav-stat"><div class="fav-stat-value">${r.avgKm}</div><div class="fav-stat-label">Km</div></div>
                    </div>
                    <div style="font-size:10px;color:#94a3b8;margin-top:8px;text-align:center;"><i class="fas fa-clock me-1"></i>Last: ${r.lastUsed}</div>
                    <button class="fav-book-btn" onclick="showSection('book-ticket')"><i class="fas fa-ticket-alt me-1"></i>Book Again</button>
                </div>
            </div>`).join('');
    } catch (e) { console.log('Fav routes:', e); }
}

// ── EMERGENCY SOS ────────────────────────────────────────────────────────
async function loadEmergencySOS() {
    const contactsEl = document.getElementById('sosContacts');
    const tipsEl = document.getElementById('sosTips');
    if (!contactsEl) return;
    try {
        const res = await fetch('/api/emergency/info', { credentials: 'include' });
        const data = await res.json();
        if (!data.success) return;

        contactsEl.innerHTML = data.contacts.map(c => `
            <div class="col-md-4 col-6">
                <div class="sos-card" onclick="window.location.href='tel:${c.number}'">
                    <div class="sos-icon" style="background:${c.color};"><i class="fas ${c.icon}"></i></div>
                    <div class="sos-name">${c.name}</div>
                    <div class="sos-number" style="color:${c.color};">${c.number}</div>
                    <div class="sos-available"><i class="fas fa-check-circle me-1"></i>${c.available}</div>
                </div>
            </div>`).join('');

        if (tipsEl && data.tips) {
            tipsEl.innerHTML = data.tips.map(t => `
                <div class="sos-tip">
                    <div class="sos-tip-icon"><i class="fas ${t.icon}"></i></div>
                    <div><div class="sos-tip-title">${t.title}</div><div class="sos-tip-desc">${t.desc}</div></div>
                </div>`).join('');
        }
    } catch (e) { console.log('SOS:', e); }
}

// ── REGISTER NEW SECTIONS WITH MUTATION OBSERVER ─────────────────────────
(function() {
    const newHandlers = {
        'fare-compare-section': () => initFareCompare(),
        'trip-calendar-section': () => loadTripCalendar(),
        'nearby-places-section': () => initNearbyPlaces(),
        'favorite-routes-section': () => loadFavoriteRoutes(),
        'emergency-sos-section': () => loadEmergencySOS()
    };
    const obs = new MutationObserver(mutations => {
        mutations.forEach(m => {
            if (m.type === 'attributes' && m.attributeName === 'style') {
                const el = m.target;
                if (el.id && newHandlers[el.id] && el.style.display !== 'none') newHandlers[el.id]();
            }
        });
    });
    function attach() {
        Object.keys(newHandlers).forEach(id => {
            const el = document.getElementById(id);
            if (el) obs.observe(el, { attributes: true, attributeFilter: ['style'] });
        });
    }
    document.addEventListener('DOMContentLoaded', () => setTimeout(attach, 600));
    window.addEventListener('load', () => setTimeout(attach, 2500));
})();

// ═══════════════════════════════════════════════════════════════════════
//  SIDEBAR GROUP COLLAPSE/EXPAND
// ═══════════════════════════════════════════════════════════════════════
window.toggleSidebarGroup = function (groupId) {
    const group = document.getElementById(groupId);
    if (!group) return;
    group.classList.toggle('collapsed');
};

// ═══════════════════════════════════════════════════════════════════════
//  FLOATING CONTEXT MENU — right-click / long-press on sidebar links
// ═══════════════════════════════════════════════════════════════════════
(function initCtxMenu() {
    const GROUPS = {
        main: [
            { icon: 'fa-th-large',    label: 'Dashboard',       section: 'dashboard'    },
            { icon: 'fa-ticket-alt',  label: 'Book Ticket',      section: 'book-ticket'  },
            { icon: 'fa-list-ul',     label: 'My Tickets',       section: 'my-tickets'   }
        ],
        finance: [
            { icon: 'fa-wallet',         label: 'Wallet',        section: 'wallet'       },
            { icon: 'fa-credit-card',    label: 'Metro Card',    section: 'metro-card'   },
            { icon: 'fa-calendar-check', label: 'Monthly Pass',  section: 'monthly-pass' },
            { icon: 'fa-exchange-alt',   label: 'Transactions',  section: 'transactions' }
        ],
        travel: [
            { icon: 'fa-route',           label: 'Journey Planner',  section: 'journey-planner'  },
            { icon: 'fa-satellite-dish',  label: 'Live Trains',       section: 'live-trains'      },
            { icon: 'fa-map-marked-alt',  label: 'Metro Map',         section: 'metro-map'        },
            { icon: 'fa-history',         label: 'Journey History',   section: 'journey-history'  },
            { icon: 'fa-calculator',      label: 'Fare Calculator',   section: 'fare-calculator'  }
        ],
        insights: [
            { icon: 'fa-chart-bar',   label: 'Analytics',          section: 'analytics'       },
            { icon: 'fa-chart-pie',   label: 'My Spending',        section: 'spending'        }
        ],
        account: [
            { icon: 'fa-user-circle', label: 'My Profile',    section: 'profile'      },
            { icon: 'fa-trophy',      label: 'Achievements',  section: 'achievements' },
            { icon: 'fa-cog',         label: 'Settings',      section: 'settings'     }
        ],
        more: [
            { icon: 'fa-comment-alt',      label: 'Feedback',        section: 'feedback'       },
            { icon: 'fa-search-location',  label: 'Lost & Found',    section: 'lost-found'     },
            { icon: 'fa-exclamation-circle',label: 'Emergency SOS',  section: 'emergency-sos'  }
        ]
    };

    const GROUP_LABELS = {
        main: 'Main', finance: 'Finance', travel: 'Travel',
        insights: 'Insights', account: 'Account', more: 'More'
    };

    let menu = null;
    let hideTimer = null;
    let longPressTimer = null;
    let currentActiveSection = 'dashboard';

    function getMenu() {
        if (!menu) menu = document.getElementById('ctxMenu');
        return menu;
    }

    function getCurrentSection() {
        // Read from active sidebar link
        const active = document.querySelector('.sidebar-link.active[data-section]');
        return active ? active.dataset.section : currentActiveSection;
    }

    function buildMenu(groupKey) {
        const m = getMenu();
        if (!m) return;

        const items = GROUPS[groupKey] || [];
        const label = GROUP_LABELS[groupKey] || groupKey;
        const activeSec = getCurrentSection();

        let html = `<div class="ctx-menu-label">${label}</div>`;

        items.forEach(item => {
            const isActive = item.section === activeSec;
            html += `
                <button class="ctx-menu-item${isActive ? ' active' : ''}"
                        onclick="showSection('${item.section}');hideCtxMenu()"
                        role="menuitem">
                    <span class="ctx-item-icon"><i class="fas ${item.icon}"></i></span>
                    <span class="ctx-item-label">${item.label}</span>
                    ${isActive ? '<i class="fas fa-check" style="font-size:10px;opacity:0.6;"></i>' : ''}
                </button>`;
        });

        m.innerHTML = html;
    }

    function positionMenu(x, y) {
        const m = getMenu();
        if (!m) return;

        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const mw = 220; // approximate menu width
        const mh = m.offsetHeight || 240;

        // Flip left if would overflow right
        const left = (x + mw > vw - 12) ? x - mw : x;
        // Flip up if would overflow bottom
        const top  = (y + mh > vh - 12) ? y - mh : y;

        m.style.left = Math.max(8, left) + 'px';
        m.style.top  = Math.max(8, top)  + 'px';
    }

    window.showCtxMenu = function (e, groupKey) {
        e.preventDefault();
        e.stopPropagation();
        if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }

        buildMenu(groupKey);

        const m = getMenu();
        if (!m) return;

        // Position off-screen first to allow measuring height
        m.style.left = '-9999px';
        m.style.top  = '-9999px';
        m.classList.remove('visible');

        requestAnimationFrame(() => {
            positionMenu(e.clientX + 6, e.clientY + 4);
            m.classList.add('visible');
        });
    };

    window.hideCtxMenu = function () {
        const m = getMenu();
        if (!m) return;
        m.classList.remove('visible');
    };

    // ── Attach to sidebar links ───────────────────────────────────────────
    function attachListeners() {
        document.querySelectorAll('.sidebar-link[data-ctx-group]').forEach(link => {
            const group = link.dataset.ctxGroup;

            // Right-click → context menu
            link.addEventListener('contextmenu', e => {
                window.showCtxMenu(e, group);
            });

            // Long-press (touch) → context menu
            link.addEventListener('touchstart', e => {
                longPressTimer = setTimeout(() => {
                    // Synthesize position from touch
                    const t = e.touches[0];
                    const fakeEvt = { clientX: t.clientX, clientY: t.clientY, preventDefault: () => {}, stopPropagation: () => {} };
                    window.showCtxMenu(fakeEvt, group);
                }, 500);
            }, { passive: true });

            link.addEventListener('touchend', () => {
                if (longPressTimer) { clearTimeout(longPressTimer); longPressTimer = null; }
            });

            link.addEventListener('touchmove', () => {
                if (longPressTimer) { clearTimeout(longPressTimer); longPressTimer = null; }
            });
        });

        // Dismiss on outside click / Escape
        document.addEventListener('click', e => {
            const m = getMenu();
            if (m && !m.contains(e.target)) window.hideCtxMenu();
        });

        document.addEventListener('keydown', e => {
            if (e.key === 'Escape') window.hideCtxMenu();
        });

        // Scroll or resize → hide
        window.addEventListener('scroll', window.hideCtxMenu, { passive: true });
        window.addEventListener('resize', window.hideCtxMenu, { passive: true });
    }

    // ── Keep active state in sync with showSection ────────────────────────
    const _origShow = window.showSection;
    if (typeof _origShow === 'function') {
        window.showSection = function (section) {
            currentActiveSection = section;
            // Update active class on sidebar links
            document.querySelectorAll('.sidebar-link[data-section]').forEach(l => {
                l.classList.toggle('active', l.dataset.section === section);
            });
            _origShow(section);
        };
    }

    // Init after DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => setTimeout(attachListeners, 800));
    } else {
        setTimeout(attachListeners, 800);
    }
})();
