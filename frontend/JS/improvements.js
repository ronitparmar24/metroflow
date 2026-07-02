/* ═══════════════════════════════════════════════════════════════════════
   METROFLOW IMPROVEMENTS — Round 2 — JavaScript
   ═══════════════════════════════════════════════════════════════════════ */

(function () {
    'use strict';

    // ── Wait for DOM + existing app to load ──────────────────────────────
    window.addEventListener('DOMContentLoaded', () => {
        setTimeout(initImprovements, 1200);
    });

    function initImprovements() {
        // injectNotificationBell(); // Disabled — navbar already has notification bell
        injectNotificationDrawer();
        injectNewSections();
        hookSectionSwitcher();
        loadWeatherCard();
        loadLiveFeed();
        loadRecommendations();
        maybeStartOnboardingTour();
    }

    // ═══════════════════════════════════════════════════════════════
    // 1. NOTIFICATION BELL (injected into navbar)
    // ═══════════════════════════════════════════════════════════════
    function injectNotificationBell() {
        // Prevent duplicate injection
        if (document.getElementById('notifBellBtn')) return;

        // Try to find the navbar right-side actions area
        const navbar = document.querySelector('.dashboard-navbar');
        if (!navbar) return;
        const container = navbar.querySelector('.container-fluid') || navbar;
        const rightSide = container.querySelector('.d-flex.align-items-center.gap-3') ||
            container.querySelector('.d-flex.align-items-center.gap-2');
        if (!rightSide) return;

        const bell = document.createElement('button');
        bell.className = 'notif-bell';
        bell.id = 'notifBellBtn';
        bell.innerHTML = '<i class="fas fa-bell"></i><span class="notif-badge hidden" id="notifBadge">0</span>';
        bell.onclick = toggleNotifDrawer;
        rightSide.insertBefore(bell, rightSide.firstChild);
        loadNotifications();
    }

    // ═══════════════════════════════════════════════════════════════
    //  NOTIFICATION DRAWER
    // ═══════════════════════════════════════════════════════════════
    let notifData = [];
    let notifFilter = 'all';

    function injectNotificationDrawer() {
        const overlay = document.createElement('div');
        overlay.className = 'notif-drawer-overlay';
        overlay.id = 'notifOverlay';
        overlay.onclick = closeNotifDrawer;

        const drawer = document.createElement('div');
        drawer.className = 'notif-drawer';
        drawer.id = 'notifDrawer';
        drawer.innerHTML = `
            <div class="notif-drawer-header">
                <h5><i class="fas fa-bell me-2"></i>Notifications</h5>
                <button class="notif-close" onclick="closeNotifDrawer()"><i class="fas fa-times"></i></button>
            </div>
            <div class="notif-tabs">
                <div class="notif-tab active" data-cat="all" onclick="filterNotifs('all',this)">All</div>
                <div class="notif-tab" data-cat="booking" onclick="filterNotifs('booking',this)">🎫 Bookings</div>
                <div class="notif-tab" data-cat="wallet" onclick="filterNotifs('wallet',this)">💰 Wallet</div>
                <div class="notif-tab" data-cat="system" onclick="filterNotifs('system',this)">📢 System</div>
                <div class="notif-tab" data-cat="alert" onclick="filterNotifs('alert',this)">⚡ Alerts</div>
            </div>
            <div class="notif-list" id="notifList"></div>
            <div class="notif-footer">
                <button onclick="markAllRead()"><i class="fas fa-check-double me-2"></i>Mark all as read</button>
            </div>
        `;
        document.body.appendChild(overlay);
        document.body.appendChild(drawer);
    }

    window.toggleNotifDrawer = function () {
        document.getElementById('notifOverlay')?.classList.toggle('open');
        document.getElementById('notifDrawer')?.classList.toggle('open');
    };
    window.closeNotifDrawer = function () {
        document.getElementById('notifOverlay')?.classList.remove('open');
        document.getElementById('notifDrawer')?.classList.remove('open');
    };

    async function loadNotifications() {
        try {
            const res = await fetch('/api/notifications/center', { credentials: 'include' });
            const data = await res.json();
            if (data.success) {
                notifData = data.notifications || [];
                const badge = document.getElementById('notifBadge');
                if (badge) {
                    if (data.unread_count > 0) {
                        badge.textContent = data.unread_count;
                        badge.classList.remove('hidden');
                    } else {
                        badge.classList.add('hidden');
                    }
                }
                renderNotifs();
            }
        } catch (e) { console.log('Notif load:', e); }
    }

    function renderNotifs() {
        const list = document.getElementById('notifList');
        if (!list) return;
        const filtered = notifFilter === 'all' ? notifData : notifData.filter(n => n.category === notifFilter);
        if (!filtered.length) {
            list.innerHTML = '<div class="notif-empty"><i class="fas fa-bell-slash d-block"></i><div>No notifications</div><small style="color:#94a3b8">You\'re all caught up!</small></div>';
            return;
        }
        list.innerHTML = filtered.map(n => `
            <div class="notif-item ${n.read ? '' : 'unread'}" id="notif-${n.id}">
                <span class="notif-icon">${n.icon}</span>
                <div class="notif-content">
                    <div class="notif-title">${n.title}</div>
                    <div class="notif-msg">${n.message}</div>
                    <div class="notif-time"><i class="fas fa-clock me-1"></i>${n.time}</div>
                </div>
            </div>
        `).join('');
    }

    window.filterNotifs = function (cat, el) {
        notifFilter = cat;
        document.querySelectorAll('.notif-tab').forEach(t => t.classList.remove('active'));
        if (el) el.classList.add('active');
        renderNotifs();
    };

    window.markAllRead = function () {
        notifData.forEach(n => n.read = true);
        const badge = document.getElementById('notifBadge');
        if (badge) badge.classList.add('hidden');
        renderNotifs();
        showToast('All notifications marked as read', 'success');
    };

    // ═══════════════════════════════════════════════════════════════
    //  INJECT NEW SECTIONS INTO MAIN CONTENT
    // ═══════════════════════════════════════════════════════════════
    function injectNewSections() {
        const mainContent = document.querySelector('.main-content');
        if (!mainContent) return;

        // Prevent duplicate injection — use achievements-section as the guard
        // since profile-section already exists in dashboard.html
        if (document.getElementById('achievements-section')) return;

        // ── Achievements Section ──
        const achSection = document.createElement('div');
        achSection.id = 'achievements-section';
        achSection.className = 'content-section';
        achSection.style.display = 'none';
        achSection.innerHTML = `
            <div class="d-flex align-items-center justify-content-between mb-4">
                <h2 class="section-title-text mb-0"><i class="fas fa-trophy me-2"></i>Achievements</h2>
                <span id="achOverallBadge" style="background:linear-gradient(135deg,#f59e0b,#d97706);color:white;padding:6px 18px;border-radius:50px;font-size:14px;font-weight:800;">0/8</span>
            </div>
            <div class="glass-card"><div id="achContent" class="ach-grid"><div class="text-center py-5" style="grid-column:1/-1"><i class="fas fa-spinner fa-spin me-2"></i>Loading achievements...</div></div></div>
        `;
        mainContent.appendChild(achSection);

        // ── Spending Section ──
        const spendSection = document.createElement('div');
        spendSection.id = 'spending-section';
        spendSection.className = 'content-section';
        spendSection.style.display = 'none';
        spendSection.innerHTML = `
            <h2 class="section-title-text mb-4"><i class="fas fa-chart-pie me-2"></i>My Spending</h2>
            <div class="row g-4">
                <div class="col-12 col-lg-5">
                    <div class="glass-card text-center">
                        <h5 class="fw-bold mb-3">Monthly Budget</h5>
                        <div class="budget-ring-container" id="budgetRing">
                            <svg viewBox="0 0 120 120"><circle cx="60" cy="60" r="52" fill="none" stroke="rgba(0,0,0,0.06)" stroke-width="10"/><circle id="budgetArc" cx="60" cy="60" r="52" fill="none" stroke="url(#budgetGrad)" stroke-width="10" stroke-linecap="round" stroke-dasharray="326.7" stroke-dashoffset="326.7" transform="rotate(-90 60 60)"/><defs><linearGradient id="budgetGrad" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#22c55e"/><stop offset="50%" stop-color="#f59e0b"/><stop offset="100%" stop-color="#ef4444"/></linearGradient></defs></svg>
                            <div class="budget-center-text">
                                <div style="font-size:28px;font-weight:900;" id="budgetSpent">₹0</div>
                                <div style="font-size:11px;color:#94a3b8;">of <span id="budgetTotal">₹0</span></div>
                            </div>
                        </div>
                        <div class="mt-3 d-flex align-items-center justify-content-center gap-2">
                            <input type="number" id="budgetInput" placeholder="Set budget..." style="width:120px;padding:8px 12px;border:1px solid rgba(0,0,0,0.1);border-radius:10px;font-size:13px;text-align:center;">
                            <button onclick="saveBudget()" style="background:linear-gradient(135deg,#667eea,#764ba2);color:white;border:none;border-radius:10px;padding:8px 16px;font-size:12px;font-weight:700;cursor:pointer;">Set</button>
                        </div>
                    </div>
                </div>
                <div class="col-12 col-lg-7">
                    <div class="glass-card mb-4">
                        <h6 class="fw-bold mb-3"><i class="fas fa-tags me-2" style="color:#667eea;"></i>Spending Categories</h6>
                        <div class="spending-cats" id="spendingCats">
                            <div class="spending-cat-item"><div class="cat-icon">🎫</div><div class="cat-amount" id="catTickets">₹0</div><div class="cat-label">Tickets</div></div>
                            <div class="spending-cat-item"><div class="cat-icon">🎟️</div><div class="cat-amount" id="catPasses">₹0</div><div class="cat-label">Passes</div></div>
                            <div class="spending-cat-item"><div class="cat-icon">💰</div><div class="cat-amount" id="catTotal">₹0</div><div class="cat-label">Total</div></div>
                        </div>
                    </div>
                    <div class="glass-card">
                        <h6 class="fw-bold mb-2"><i class="fas fa-leaf me-2" style="color:#22c55e;"></i>Smart Savings</h6>
                        <div class="d-flex align-items-center gap-3" style="background:rgba(34,197,94,0.06);border-radius:14px;padding:16px;">
                            <div style="font-size:32px;">🌿</div>
                            <div>
                                <div style="font-size:20px;font-weight:900;color:#22c55e;" id="offpeakSavings">₹0</div>
                                <div style="font-size:12px;color:#94a3b8;">saved by off-peak travel</div>
                            </div>
                        </div>
                        <div class="row g-2 mt-2">
                            <div class="col-6">
                                <div style="background:rgba(102,126,234,0.05);border-radius:12px;padding:12px;text-align:center;">
                                    <div style="font-size:18px;font-weight:800;color:#667eea;" id="avgTripCost">₹0</div>
                                    <div style="font-size:10px;color:#94a3b8;">Avg Trip Cost</div>
                                </div>
                            </div>
                            <div class="col-6">
                                <div style="background:rgba(245,87,108,0.05);border-radius:12px;padding:12px;text-align:center;">
                                    <div style="font-size:18px;font-weight:800;color:#f5576c;" id="monthTripsCount">0</div>
                                    <div style="font-size:10px;color:#94a3b8;">This Month's Trips</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        mainContent.appendChild(spendSection);

        // ── Settings Section ──
        const settingsSection = document.createElement('div');
        settingsSection.id = 'settings-section';
        settingsSection.className = 'content-section';
        settingsSection.style.display = 'none';
        settingsSection.innerHTML = `
            <h2 class="section-title-text mb-4"><i class="fas fa-cog me-2"></i>Settings</h2>
            <div class="glass-card">
                <div class="settings-group">
                    <h6><i class="fas fa-palette me-2"></i>Appearance</h6>
                    <div class="setting-row">
                        <div><div class="setting-label">Dark Mode</div><div class="setting-desc">Toggle dark/light theme</div></div>
                        <label class="toggle-switch"><input type="checkbox" id="settingsDarkMode" onchange="toggleSettingsDarkMode()"><span class="toggle-slider"></span></label>
                    </div>
                </div>
                <div class="settings-group">
                    <h6><i class="fas fa-bell me-2"></i>Notifications</h6>
                    <div class="setting-row">
                        <div><div class="setting-label">Booking Alerts</div><div class="setting-desc">Get notified about bookings</div></div>
                        <label class="toggle-switch"><input type="checkbox" id="settingsNotifBooking" checked onchange="saveSettings()"><span class="toggle-slider"></span></label>
                    </div>
                    <div class="setting-row">
                        <div><div class="setting-label">Wallet Alerts</div><div class="setting-desc">Low balance warnings</div></div>
                        <label class="toggle-switch"><input type="checkbox" id="settingsNotifWallet" checked onchange="saveSettings()"><span class="toggle-slider"></span></label>
                    </div>
                    <div class="setting-row">
                        <div><div class="setting-label">System Updates</div><div class="setting-desc">Announcements & maintenance</div></div>
                        <label class="toggle-switch"><input type="checkbox" id="settingsNotifSystem" checked onchange="saveSettings()"><span class="toggle-slider"></span></label>
                    </div>
                </div>
                <div class="settings-group">
                    <h6><i class="fas fa-lock me-2"></i>Account</h6>
                    <div class="setting-row">
                        <div><div class="setting-label">Change Password</div><div class="setting-desc">Update your account password</div></div>
                        <button onclick="showSection('profile')" style="background:linear-gradient(135deg,#667eea,#764ba2);color:white;border:none;border-radius:10px;padding:6px 16px;font-size:12px;font-weight:700;cursor:pointer;">Change</button>
                    </div>
                </div>
            </div>
        `;
        mainContent.appendChild(settingsSection);

        // ── Eco Tracker Section ──
        const ecoSection = document.createElement('div');
        ecoSection.id = 'eco-section';
        ecoSection.className = 'content-section';
        ecoSection.style.display = 'none';
        ecoSection.innerHTML = `
            <h2 class="section-title-text mb-4"><i class="fas fa-leaf me-2"></i>Eco Impact</h2>
            <div id="ecoContent"><div class="glass-card text-center py-5"><i class="fas fa-spinner fa-spin me-2"></i>Calculating your impact...</div></div>
        `;
        mainContent.appendChild(ecoSection);

        // ── Journey Planner Section ──
        const jpSection = document.createElement('div');
        jpSection.id = 'journey-planner-section';
        jpSection.className = 'content-section';
        jpSection.style.display = 'none';
        jpSection.innerHTML = `
            <h2 class="section-title-text mb-4"><i class="fas fa-route me-2"></i>Journey Planner</h2>
            <div class="glass-card">
                <div class="row g-3 mb-4">
                    <div class="col-12 col-md-5">
                        <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:#94a3b8;letter-spacing:0.5px;">From Station</label>
                        <select id="jpSource" class="form-select" style="border-radius:12px;padding:10px 14px;font-weight:600;"></select>
                    </div>
                    <div class="col-12 col-md-2 d-flex align-items-end justify-content-center">
                        <button onclick="swapJPStations()" style="background:linear-gradient(135deg,#667eea,#764ba2);color:white;border:none;border-radius:12px;width:44px;height:44px;font-size:16px;cursor:pointer;" title="Swap"><i class="fas fa-exchange-alt"></i></button>
                    </div>
                    <div class="col-12 col-md-5">
                        <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:#94a3b8;letter-spacing:0.5px;">To Station</label>
                        <select id="jpDest" class="form-select" style="border-radius:12px;padding:10px 14px;font-weight:600;"></select>
                    </div>
                </div>
                <button onclick="planJourney()" class="btn w-100" style="background:linear-gradient(135deg,#667eea,#764ba2);color:white;border:none;border-radius:14px;padding:14px;font-size:15px;font-weight:800;"><i class="fas fa-search me-2"></i>Find Best Route</button>
            </div>
            <div id="jpResult" class="mt-4"></div>
        `;
        mainContent.appendChild(jpSection);

        // ── Streaks Section ──
        const streaksSection = document.createElement('div');
        streaksSection.id = 'streaks-section';
        streaksSection.className = 'content-section';
        streaksSection.style.display = 'none';
        streaksSection.innerHTML = `
            <h2 class="section-title-text mb-4"><i class="fas fa-fire me-2"></i>Travel Streaks</h2>
            <div id="streaksContent"><div class="glass-card text-center py-5"><i class="fas fa-spinner fa-spin me-2"></i>Loading streaks...</div></div>
        `;
        mainContent.appendChild(streaksSection);
    }

    // ═══════════════════════════════════════════════════════════════
    //  HOOK INTO showSection()
    // ═══════════════════════════════════════════════════════════════
    function hookSectionSwitcher() {
        const origShow = window.showSection;
        const customSections = ['achievements', 'spending', 'settings', 'eco', 'journey-planner', 'streaks'];
        window.showSection = function (section) {
            // Hide our custom sections
            customSections.forEach(s => {
                const el = document.getElementById(s + '-section');
                if (el) el.style.display = 'none';
            });

            if (customSections.includes(section)) {
                // Hide all original sections
                document.querySelectorAll('.content-section').forEach(s => s.style.display = 'none');
                const target = document.getElementById(section + '-section');
                if (target) {
                    target.style.display = 'block';
                    target.style.animation = 'fadeIn 0.5s ease';
                }
                // Update sidebar active
                document.querySelectorAll('.sidebar-link').forEach(l => l.classList.remove('active'));
                const link = document.querySelector(`.sidebar-link[onclick*="'${section}'"]`);
                if (link) link.classList.add('active');

                // Load data for the section
                if (section === 'profile') loadProfile();
                if (section === 'achievements') loadAchievements();
                if (section === 'spending') loadSpending();
                if (section === 'settings') loadSettings();
                if (section === 'eco') loadEcoTracker();
                if (section === 'journey-planner') loadJourneyPlanner();
                if (section === 'streaks') loadStreaks();

                // Close mobile sidebar
                if (typeof closeSidebar === 'function') closeSidebar();
            } else {
                if (typeof origShow === 'function') origShow(section);
            }
        };
    }

    // ═══════════════════════════════════════════════════════════════
    //  2. PROFILE LOADER
    // ═══════════════════════════════════════════════════════════════
    async function loadProfile() {
        try {
            const res = await fetch('/api/user/profile', { credentials: 'include' });
            const data = await res.json();
            if (!data.success) return;
            const p = data.profile;
            const initials = (p.username || 'U').substring(0, 2).toUpperCase();
            const container = document.getElementById('profileContent');
            container.innerHTML = `
                <div class="profile-header-card">
                    <div class="d-flex align-items-center gap-4 position-relative z-1">
                        <div class="profile-avatar">${initials}</div>
                        <div>
                            <h3 class="mb-1 fw-bold">${p.username}</h3>
                            <div class="profile-tier-badge">${p.tier.icon} ${p.tier.name} Member</div>
                            <div style="font-size:12px;opacity:0.8;margin-top:6px;">
                                <i class="fas fa-calendar-alt me-1"></i>Member since ${p.join_date ? new Date(p.join_date).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' }) : 'Recently'}
                            </div>
                        </div>
                    </div>
                    <div class="profile-stats-grid">
                        <div class="profile-stat-item"><div class="stat-num">${p.total_trips}</div><div class="stat-label">Total Trips</div></div>
                        <div class="profile-stat-item"><div class="stat-num">₹${Math.round(p.total_spent)}</div><div class="stat-label">Total Spent</div></div>
                        <div class="profile-stat-item"><div class="stat-num">${p.co2_saved} kg</div><div class="stat-label">CO₂ Saved</div></div>
                        <div class="profile-stat-item"><div class="stat-num">${p.loyalty_points}</div><div class="stat-label">Loyalty Points</div></div>
                    </div>
                </div>
                <div class="glass-card mb-4">
                    <h5 class="fw-bold mb-3"><i class="fas fa-star me-2" style="color:#f59e0b;"></i>Favorite Stations</h5>
                    ${p.favorite_stations.length ? p.favorite_stations.map((s, i) => `
                        <div class="d-flex align-items-center justify-content-between" style="padding:10px 0;${i < p.favorite_stations.length - 1 ? 'border-bottom:1px solid rgba(0,0,0,0.05);' : ''}">
                            <div class="d-flex align-items-center gap-3">
                                <div style="width:32px;height:32px;border-radius:10px;background:linear-gradient(135deg,${['#667eea', '#f093fb', '#4facfe'][i]},${['#764ba2', '#f5576c', '#00f2fe'][i]});display:flex;align-items:center;justify-content:center;color:white;font-size:12px;font-weight:800;">${i + 1}</div>
                                <span style="font-weight:600;font-size:14px;">${s.name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</span>
                            </div>
                            <span style="font-size:12px;color:#94a3b8;font-weight:700;">${s.trips} trips</span>
                        </div>
                    `).join('') : '<div style="color:#94a3b8;text-align:center;padding:20px;">No trips yet. Start traveling to see your favorites!</div>'}
                </div>
                <div class="glass-card">
                    <h5 class="fw-bold mb-3"><i class="fas fa-wallet me-2" style="color:#22c55e;"></i>Wallet Balance</h5>
                    <div style="font-size:36px;font-weight:900;background:linear-gradient(135deg,#667eea,#764ba2);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">₹${p.balance.toFixed(2)}</div>
                    <button onclick="showSection('wallet')" style="margin-top:12px;background:linear-gradient(135deg,#667eea,#764ba2);color:white;border:none;border-radius:12px;padding:10px 24px;font-size:13px;font-weight:700;cursor:pointer;">
                        <i class="fas fa-plus me-2"></i>Top Up Wallet
                    </button>
                </div>
            `;
        } catch (e) { console.log('Profile load:', e); }
    }

    // ═══════════════════════════════════════════════════════════════
    //  3. ACHIEVEMENTS LOADER
    // ═══════════════════════════════════════════════════════════════
    async function loadAchievements() {
        try {
            const res = await fetch('/api/user/achievements', { credentials: 'include' });
            const data = await res.json();
            if (!data.success) return;

            const badge = document.getElementById('achOverallBadge');
            if (badge) badge.textContent = `${data.unlocked || 0}/${data.total || 0}`;

            const grid = document.getElementById('achContent');
            if (!grid) return;

            const badges = data.badges || [];
            if (badges.length === 0) {
                grid.innerHTML = '<div style="text-align:center;padding:30px;color:#94a3b8;grid-column:1/-1;"><i class="fas fa-trophy" style="font-size:32px;opacity:0.3;display:block;margin-bottom:10px;"></i>Start traveling to unlock achievements!</div>';
                return;
            }

            grid.innerHTML = badges.map(b => {
                const pct = b.target > 0 ? Math.round((b.progress / b.target) * 100) : 0;
                return `
                    <div class="ach-badge ${b.unlocked ? 'unlocked' : 'locked'}">
                        <span class="ach-icon">${b.icon}</span>
                        <div class="ach-name">${b.name}</div>
                        <div class="ach-desc">${b.desc}</div>
                        <div class="ach-progress-bar"><div class="ach-progress-fill" style="width:${pct}%"></div></div>
                        <div class="ach-progress-text">${b.progress}/${b.target} ${b.unlocked ? '✅' : ''}</div>
                    </div>
                `;
            }).join('');

            // Check for new unlocks (confetti!)
            if (data.unlocked > 0) {
                const prev = parseInt(localStorage.getItem('mf_ach_count') || '0');
                if (data.unlocked > prev) {
                    if (typeof launchConfetti === 'function') launchConfetti();
                    if (typeof showToast === 'function') showToast(`🏆 Achievement Unlocked!`, 'success');
                }
                localStorage.setItem('mf_ach_count', data.unlocked);
            }
        } catch (e) { console.log('Achievements load:', e); }
    }

    // ═══════════════════════════════════════════════════════════════
    //  7. SPENDING LOADER
    // ═══════════════════════════════════════════════════════════════
    async function loadSpending() {
        try {
            const res = await fetch('/api/user/spending-insights', { credentials: 'include' });
            const data = await res.json();
            if (!data.success) return;

            const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
            setEl('catTickets', `₹${Math.round(data.categories.tickets)}`);
            setEl('catPasses', `₹${Math.round(data.categories.passes)}`);
            setEl('catTotal', `₹${Math.round(data.categories.recharges)}`);
            setEl('offpeakSavings', `₹${data.offpeak_savings}`);
            setEl('avgTripCost', `₹${data.avg_trip_cost}`);
            setEl('monthTripsCount', data.month_trips);

            // Budget ring
            const budget = data.budget || 0;
            const spent = data.month_spent || 0;
            setEl('budgetSpent', `₹${Math.round(spent)}`);
            setEl('budgetTotal', budget > 0 ? `₹${budget}` : 'No budget set');
            if (budget > 0) {
                const pct = Math.min(spent / budget, 1);
                const arc = document.getElementById('budgetArc');
                if (arc) arc.style.strokeDashoffset = 326.7 * (1 - pct);
            }
            const budgetInput = document.getElementById('budgetInput');
            if (data.budget && budgetInput) budgetInput.value = data.budget;
        } catch (e) { console.log('Spending load:', e); }
    }

    window.saveBudget = async function () {
        const val = parseInt(document.getElementById('budgetInput').value);
        if (!val || val < 100) { showToast('Set a budget of ₹100 or more', 'warning'); return; }
        try {
            const res = await fetch('/api/user/budget', {
                method: 'PUT', credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ budget: val })
            });
            const data = await res.json();
            if (data.success) { showToast('Budget saved!', 'success'); loadSpending(); }
        } catch (e) { showToast('Error saving budget', 'error'); }
    };

    // ═══════════════════════════════════════════════════════════════
    //  SETTINGS
    // ═══════════════════════════════════════════════════════════════
    function loadSettings() {
        const dm = document.getElementById('settingsDarkMode');
        if (dm) dm.checked = document.body.classList.contains('dark-mode');
    }

    window.toggleSettingsDarkMode = function () {
        const dm = document.getElementById('settingsDarkMode');
        if (dm.checked) document.body.classList.add('dark-mode');
        else document.body.classList.remove('dark-mode');
        localStorage.setItem('darkMode', dm.checked);
        saveSettings();
    };

    window.saveSettings = async function () {
        try {
            await fetch('/api/user/profile/preferences', {
                method: 'PUT', credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    theme: document.body.classList.contains('dark-mode') ? 'dark' : 'light',
                    notif_booking: document.getElementById('settingsNotifBooking')?.checked ?? true,
                    notif_wallet: document.getElementById('settingsNotifWallet')?.checked ?? true,
                    notif_system: document.getElementById('settingsNotifSystem')?.checked ?? true,
                })
            });
        } catch (e) { /* silent */ }
    };

    // ═══════════════════════════════════════════════════════════════
    //  9. WEATHER CARD (on dashboard)
    // ═══════════════════════════════════════════════════════════════
    async function loadWeatherCard() {
        try {
            const res = await fetch('/api/travel/weather-advisory', { credentials: 'include' });
            const data = await res.json();
            if (!data.success) return;
            const w = data.weather;

            const dashSection = document.getElementById('dashboard-section');
            if (!dashSection) return;

            const existing = document.getElementById('weatherAdvisoryCard');
            if (existing) existing.remove();

            // Dynamic gradient based on weather condition
            const condLower = (w.condition || '').toLowerCase();
            let bgGrad = 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)';
            let iconBg = 'rgba(255,255,255,0.2)';
            if (condLower.includes('rain') || condLower.includes('storm')) {
                bgGrad = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
            } else if (condLower.includes('cloud') || condLower.includes('overcast')) {
                bgGrad = 'linear-gradient(135deg, #89a0c4 0%, #b8cce2 100%)';
            } else if (condLower.includes('hot') || condLower.includes('sunny') || condLower.includes('clear')) {
                bgGrad = 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)';
            } else if (condLower.includes('fog') || condLower.includes('haze') || condLower.includes('mist')) {
                bgGrad = 'linear-gradient(135deg, #a8c0b8 0%, #c4d4cf 100%)';
            }

            const humidity = w.humidity || Math.floor(40 + Math.random() * 40);
            const wind = w.wind || Math.floor(5 + Math.random() * 20);

            const card = document.createElement('div');
            card.id = 'weatherAdvisoryCard';
            card.className = 'weather-card-premium';
            card.setAttribute('data-aos', 'fade-up');
            card.innerHTML = `
                <div class="weather-hero" style="background:${bgGrad};">
                    <div class="weather-hero-content">
                        <div class="weather-hero-left">
                            <div class="weather-icon-big">${w.icon}</div>
                            <div>
                                <div class="weather-temp-big">${w.temp}°C</div>
                                <div class="weather-condition-label">${w.condition}</div>
                            </div>
                        </div>
                        <div class="weather-hero-right">
                            <div class="weather-best-pill">
                                <i class="fas fa-clock" style="font-size:10px;"></i>
                                <span>Best: ${w.best_time}</span>
                            </div>
                        </div>
                    </div>
                    <div class="weather-stats-row">
                        <div class="weather-stat-chip">
                            <i class="fas fa-tint"></i> ${humidity}%
                        </div>
                        <div class="weather-stat-chip">
                            <i class="fas fa-wind"></i> ${wind} km/h
                        </div>
                        <div class="weather-stat-chip">
                            <i class="fas fa-temperature-high"></i> Feels ${w.temp > 30 ? 'warm' : w.temp < 15 ? 'cold' : 'pleasant'}
                        </div>
                    </div>
                </div>
                <div class="weather-advisory-strip">
                    <i class="fas fa-umbrella" style="color:#4facfe;flex-shrink:0;"></i>
                    <span>${w.advisory}</span>
                    ${w.warning ? `<span style="color:#ef4444;font-weight:700;margin-left:auto;white-space:nowrap;"><i class="fas fa-exclamation-triangle me-1"></i>${w.warning}</span>` : ''}
                </div>
            `;
            const insertAfter = dashSection.querySelector('#lowBalanceWarning') || dashSection.querySelector('#smartGreetingBanner');
            if (insertAfter && insertAfter.parentNode) {
                insertAfter.parentNode.insertBefore(card, insertAfter.nextSibling);
            } else {
                dashSection.insertBefore(card, dashSection.children[1]);
            }
        } catch (e) { console.log('Weather:', e); }
    }

    // ═══════════════════════════════════════════════════════════════
    //  5. FARE COMPARISON (injected into book-ticket section)
    // ═══════════════════════════════════════════════════════════════
    // This hooks into the existing book ticket section when fare is calculated
    window.loadFareComparison = async function (source, destination) {
        if (!source || !destination || source === destination) return;
        try {
            const res = await fetch(`/api/fare/compare?source=${encodeURIComponent(source)}&destination=${encodeURIComponent(destination)}`, { credentials: 'include' });
            const data = await res.json();
            if (!data.success) return;

            let container = document.getElementById('fareCompareContainer');
            if (!container) {
                container = document.createElement('div');
                container.id = 'fareCompareContainer';
                container.className = 'glass-card mt-3';
                container.setAttribute('data-aos', 'fade-up');
                const bookSection = document.getElementById('book-ticket-section');
                if (bookSection) bookSection.appendChild(container);
            }

            container.innerHTML = `
                <div class="d-flex align-items-center gap-2 mb-3">
                    <i class="fas fa-balance-scale" style="color:#667eea;font-size:18px;"></i>
                    <h6 class="mb-0 fw-bold">Compare Travel Options</h6>
                </div>
                <div class="fare-compare-grid">
                    <div class="fare-compare-card recommended" style="background:rgba(34,197,94,0.04);">
                        <div class="fc-best-tag">BEST VALUE</div>
                        <div class="fc-icon">🚇</div>
                        <div class="fc-mode">Metro</div>
                        <div class="fc-fare" style="color:#22c55e;">₹${data.metro.fare}</div>
                        <div class="fc-time"><i class="fas fa-clock me-1"></i>${data.metro.time}</div>
                        <div class="fc-co2">🌿 ${data.metro.co2} kg CO₂</div>
                    </div>
                    <div class="fare-compare-card" style="background:rgba(245,158,11,0.04);">
                        <div class="fc-icon">🛺</div>
                        <div class="fc-mode">Auto</div>
                        <div class="fc-fare" style="color:#f59e0b;">₹${data.auto.fare}</div>
                        <div class="fc-time"><i class="fas fa-clock me-1"></i>${data.auto.time}</div>
                        <div class="fc-co2">💨 ${data.auto.co2} kg CO₂</div>
                    </div>
                    <div class="fare-compare-card" style="background:rgba(239,68,68,0.04);">
                        <div class="fc-icon">🚕</div>
                        <div class="fc-mode">Cab</div>
                        <div class="fc-fare" style="color:#ef4444;">₹${data.cab.fare}</div>
                        <div class="fc-time"><i class="fas fa-clock me-1"></i>${data.cab.time}</div>
                        <div class="fc-co2">💨 ${data.cab.co2} kg CO₂</div>
                    </div>
                </div>
                <div style="margin-top:14px;background:linear-gradient(135deg,rgba(34,197,94,0.08),rgba(34,197,94,0.02));border-radius:14px;padding:14px 18px;display:flex;align-items:center;gap:12px;">
                    <div style="font-size:24px;">💰</div>
                    <div>
                        <div style="font-size:14px;font-weight:800;color:#22c55e;">Save ₹${data.savings.vs_cab} vs Cab!</div>
                        <div style="font-size:11px;color:#94a3b8;">Travel this route daily? Save ₹${data.savings.monthly_vs_cab}/month with a <a href="#" onclick="showSection('monthly-pass')" style="color:#667eea;">monthly pass →</a></div>
                    </div>
                </div>
            `;
        } catch (e) { console.log('Fare compare:', e); }
    };

    // ═══════════════════════════════════════════════════════════════
    //  6. GROUP BOOKING (inject toggle into book-ticket)
    // ═══════════════════════════════════════════════════════════════
    let groupPassengers = [];

    window.toggleGroupMode = function () {
        const container = document.getElementById('groupBookingContainer');
        if (container) {
            container.style.display = container.style.display === 'none' ? 'block' : 'none';
            if (container.style.display !== 'none' && groupPassengers.length === 0) addGroupPassenger();
        }
    };

    window.addGroupPassenger = function () {
        if (groupPassengers.length >= 5) { showToast('Maximum 5 passengers', 'warning'); return; }
        groupPassengers.push({ name: '' });
        renderGroupPassengers();
    };

    window.removeGroupPassenger = function (idx) {
        groupPassengers.splice(idx, 1);
        renderGroupPassengers();
    };

    function renderGroupPassengers() {
        const list = document.getElementById('groupPassengerList');
        if (!list) return;
        list.innerHTML = groupPassengers.map((p, i) => `
            <div class="group-passenger-row">
                <span style="font-weight:800;color:#667eea;font-size:13px;width:24px;">${i + 1}.</span>
                <input type="text" placeholder="Passenger name" value="${p.name}" onchange="groupPassengers[${i}].name=this.value">
                ${groupPassengers.length > 1 ? `<button class="group-remove-btn" onclick="removeGroupPassenger(${i})"><i class="fas fa-times"></i></button>` : ''}
            </div>
        `).join('');
    }

    // ═══════════════════════════════════════════════════════════════
    //  10. ONBOARDING TOUR
    // ═══════════════════════════════════════════════════════════════
    const TOUR_STEPS = [
        { target: '.sidebar', title: 'Welcome to MetroFlow! 🚇', desc: 'Navigate between sections using this sidebar. Book tickets, manage your wallet, and track achievements here.', position: 'right' },
        { target: '.sidebar-link[onclick*="book-ticket"]', title: 'Book Your Trip 🎫', desc: 'Quickly book metro tickets with smart fare calculation, route comparison, and group booking support.', position: 'right' },
        { target: '.sidebar-link[onclick*="wallet"]', title: 'Manage Your Wallet 💰', desc: 'Top up your balance, view transactions, and track spending insights — all in one place.', position: 'right' },
        { target: '.sidebar-link[onclick*="metro-card"]', title: 'Your Digital Metro Card 💳', desc: 'Tap to flip your virtual metro card — check balance, NFC status, and recent transactions.', position: 'right' },
        { target: '.sidebar-link[onclick*="achievements"]', title: 'Earn Achievements 🏆', desc: 'Unlock badges as you travel! Complete challenges, build streaks, and become a Metro Champion.', position: 'right' },
        { target: '#notifBellBtn', title: 'Stay Updated 🔔', desc: 'Click the bell to see booking confirmations, wallet alerts, and system announcements. You\'re all set!', position: 'bottom' },
    ];

    let tourStep = 0;

    function maybeStartOnboardingTour() {
        if (localStorage.getItem('metroflow_tour_completed')) return;
        setTimeout(() => startTour(), 2500);
    }

    function startTour() {
        tourStep = 0;
        showTourStep();
    }

    function showTourStep() {
        // Remove previous
        document.getElementById('tourOverlay')?.remove();
        document.getElementById('tourTooltip')?.remove();

        if (tourStep >= TOUR_STEPS.length) {
            localStorage.setItem('metroflow_tour_completed', 'true');
            showToast('Tour complete! Enjoy MetroFlow 🚇', 'success');
            return;
        }

        const step = TOUR_STEPS[tourStep];
        const el = document.querySelector(step.target);
        if (!el) { tourStep++; showTourStep(); return; }

        const rect = el.getBoundingClientRect();

        // Overlay
        const overlay = document.createElement('div');
        overlay.id = 'tourOverlay';
        overlay.className = 'tour-overlay';
        document.body.appendChild(overlay);

        // Spotlight
        const spot = document.createElement('div');
        spot.className = 'tour-spotlight';
        spot.style.cssText = `top:${rect.top - 8}px;left:${rect.left - 8}px;width:${rect.width + 16}px;height:${rect.height + 16}px;`;
        overlay.appendChild(spot);

        // Tooltip
        const tip = document.createElement('div');
        tip.id = 'tourTooltip';
        tip.className = 'tour-tooltip';
        let tipTop = rect.bottom + 16;
        let tipLeft = rect.left;
        if (step.position === 'right') { tipLeft = rect.right + 16; tipTop = rect.top; }
        if (tipLeft + 320 > window.innerWidth) tipLeft = window.innerWidth - 340;
        if (tipTop + 200 > window.innerHeight) tipTop = window.innerHeight - 220;
        tip.style.cssText = `top:${Math.max(10, tipTop)}px;left:${Math.max(10, tipLeft)}px;`;

        const dots = TOUR_STEPS.map((_, i) => `<div class="tour-dot ${i === tourStep ? 'active' : ''}"></div>`).join('');
        tip.innerHTML = `
            <h4>${step.title}</h4>
            <p>${step.desc}</p>
            <div class="tour-dots">${dots}</div>
            <div class="tour-btns">
                <button class="tour-btn-skip" onclick="endTour()">Skip</button>
                <button class="tour-btn-next" onclick="nextTourStep()">${tourStep === TOUR_STEPS.length - 1 ? 'Finish! 🎉' : 'Next →'}</button>
            </div>
        `;
        document.body.appendChild(tip);
    }

    window.nextTourStep = function () { tourStep++; showTourStep(); };
    window.endTour = function () {
        document.getElementById('tourOverlay')?.remove();
        document.getElementById('tourTooltip')?.remove();
        localStorage.setItem('metroflow_tour_completed', 'true');
    };

    // ═══════════════════════════════════════════════════════════════
    //  UTILITIES
    // ═══════════════════════════════════════════════════════════════
    function showToast(msg, type) {
        const colors = { success: '#22c55e', warning: '#f59e0b', error: '#ef4444', info: '#667eea' };
        const toast = document.createElement('div');
        toast.style.cssText = `position:fixed;bottom:30px;right:30px;background:${colors[type] || '#667eea'};color:white;padding:14px 24px;border-radius:14px;font-size:14px;font-weight:700;z-index:99999;box-shadow:0 10px 30px rgba(0,0,0,0.2);animation:notifSlideIn 0.4s ease;max-width:320px;`;
        toast.textContent = msg;
        document.body.appendChild(toast);
        setTimeout(() => { toast.style.opacity = '0'; toast.style.transition = 'opacity 0.3s'; setTimeout(() => toast.remove(), 300); }, 3000);
    }

    function launchConfetti() {
        const colors = ['#667eea', '#f59e0b', '#ef4444', '#22c55e', '#764ba2', '#f093fb', '#4facfe'];
        for (let i = 0; i < 50; i++) {
            const piece = document.createElement('div');
            piece.className = 'confetti-piece';
            piece.style.cssText = `left:${Math.random() * 100}vw;top:-10px;background:${colors[Math.floor(Math.random() * colors.length)]};width:${6 + Math.random() * 8}px;height:${6 + Math.random() * 8}px;border-radius:${Math.random() > 0.5 ? '50%' : '2px'};animation-delay:${Math.random() * 0.5}s;animation-duration:${2 + Math.random() * 2}s;`;
            document.body.appendChild(piece);
            setTimeout(() => piece.remove(), 4000);
        }
    }

    // ═══════════════════════════════════════════════════════════════
    //  LIVE BOOKING FEED (Queue from ds.py)
    // ═══════════════════════════════════════════════════════════════
    async function loadLiveFeed() {
        try {
            const res = await fetch('/api/bookings/live-feed');
            const data = await res.json();
            if (!data.success || !data.feed.length) return;

            const dashSection = document.getElementById('dashboard-section');
            if (!dashSection) return;

            let container = document.getElementById('liveFeedTicker');
            if (!container) {
                container = document.createElement('div');
                container.id = 'liveFeedTicker';
                container.className = 'live-feed-ticker';
                const weatherCard = document.getElementById('weatherAdvisoryCard');
                if (weatherCard && weatherCard.parentNode) {
                    weatherCard.parentNode.insertBefore(container, weatherCard.nextSibling);
                } else {
                    dashSection.insertBefore(container, dashSection.children[2]);
                }
            }

            const items = data.feed.slice(0, 5).map((b, i) => `
                <div class="live-feed-item" style="animation-delay:${i * 0.15}s">
                    <div class="live-feed-dot"></div>
                    <div class="live-feed-text">
                        <span class="live-feed-user">${b.user}</span> booked 
                        <span class="live-feed-route">${b.source} → ${b.destination}</span>
                        <span class="live-feed-meta">• ${b.passengers} pax • ₹${b.fare}</span>
                    </div>
                </div>
            `).join('');

            container.innerHTML = `
                <div class="live-feed-header">
                    <span class="live-feed-pulse"></span>
                    <span style="font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:0.5px;">Live Bookings</span>
                    <span style="font-size:11px;color:#94a3b8;margin-left:auto;">${data.queueSize} in queue</span>
                </div>
                <div class="live-feed-list">${items}</div>
            `;

            // Auto-refresh every 15s
            setTimeout(loadLiveFeed, 15000);
        } catch (e) { console.log('Live feed:', e); }
    }

    // ═══════════════════════════════════════════════════════════════
    //  SMART RECOMMENDATIONS (on dashboard)
    // ═══════════════════════════════════════════════════════════════
    async function loadRecommendations() {
        try {
            const res = await fetch('/api/recommendations', { credentials: 'include' });
            const data = await res.json();
            if (!data.success || !data.tips.length) return;

            const dashSection = document.getElementById('dashboard-section');
            if (!dashSection) return;

            let container = document.getElementById('smartTipsCard');
            if (!container) {
                container = document.createElement('div');
                container.id = 'smartTipsCard';
                container.className = 'smart-tips-card glass-card';
                const liveFeed = document.getElementById('liveFeedTicker');
                if (liveFeed && liveFeed.parentNode) {
                    liveFeed.parentNode.insertBefore(container, liveFeed.nextSibling);
                } else {
                    dashSection.appendChild(container);
                }
            }

            const typeColors = {
                savings: '#22c55e', timing: '#f59e0b', wallet: '#ef4444',
                action: '#667eea', upgrade: '#764ba2', discovery: '#4facfe',
                rewards: '#f59e0b', convenience: '#818cf8'
            };

            container.innerHTML = `
                <h6 class="fw-bold mb-3"><i class="fas fa-lightbulb me-2" style="color:#f59e0b;"></i>Smart Tips For You</h6>
                ${data.tips.slice(0, 3).map(tip => `
                    <div class="smart-tip-item">
                        <div class="smart-tip-icon" style="background:${typeColors[tip.type] || '#667eea'}20;">
                            <span style="font-size:20px;">${tip.icon}</span>
                        </div>
                        <div class="smart-tip-content">
                            <div class="smart-tip-title">${tip.title}</div>
                            <div class="smart-tip-desc">${tip.desc}</div>
                        </div>
                        <span class="smart-tip-priority" style="background:${tip.priority === 'high' ? '#ef4444' : tip.priority === 'medium' ? '#f59e0b' : '#94a3b8'};">${tip.priority}</span>
                    </div>
                `).join('')}
            `;
        } catch (e) { console.log('Recommendations:', e); }
    }

    // ═══════════════════════════════════════════════════════════════
    //  ECO TRACKER
    // ═══════════════════════════════════════════════════════════════
    async function loadEcoTracker() {
        try {
            const res = await fetch('/api/user/carbon-footprint', { credentials: 'include' });
            const data = await res.json();
            if (!data.success) return;

            const container = document.getElementById('ecoContent');
            if (!container) return;

            const weekly = data.weekly_activity || [];
            const rankPct = data.eco_rank_pct || 0;

            container.innerHTML = `
                <div class="carbon-hero">
                    <div style="position:relative;z-index:1;">
                        <div class="d-flex align-items-center gap-3 mb-3">
                            <div style="font-size:42px;">🌍</div>
                            <div>
                                <h3 class="fw-bold mb-0">Your Eco Impact</h3>
                                <div style="opacity:0.8;font-size:13px;">${data.total_trips} metro trips • ${data.total_distance} km traveled</div>
                            </div>
                        </div>
                        <div style="font-size:48px;font-weight:900;">${data.co2_saved} kg</div>
                        <div style="font-size:14px;opacity:0.8;">CO₂ saved vs driving</div>
                        <div style="margin-top:12px;background:rgba(255,255,255,0.2);border-radius:50px;padding:6px 16px;display:inline-flex;align-items:center;gap:8px;font-size:13px;font-weight:700;">
                            <span>🏆</span> Top ${100 - rankPct}% of commuters
                        </div>
                    </div>
                </div>
                <div class="carbon-stat-grid">
                    <div class="carbon-stat-card"><div class="carbon-stat-icon">🌿</div><div class="carbon-stat-value">${data.co2_saved} kg</div><div class="carbon-stat-label">CO₂ Saved</div></div>
                    <div class="carbon-stat-card"><div class="carbon-stat-icon">🌳</div><div class="carbon-stat-value">${data.trees_equivalent}</div><div class="carbon-stat-label">Trees Equivalent</div></div>
                    <div class="carbon-stat-card"><div class="carbon-stat-icon">⛽</div><div class="carbon-stat-value">${data.fuel_saved} L</div><div class="carbon-stat-label">Fuel Saved</div></div>
                    <div class="carbon-stat-card"><div class="carbon-stat-icon">🔥</div><div class="carbon-stat-value">${data.green_streak}</div><div class="carbon-stat-label">Day Streak</div></div>
                </div>
                ${weekly.length ? `
                <div class="glass-card mt-4">
                    <h6 class="fw-bold mb-3"><i class="fas fa-calendar-week me-2" style="color:#059669;"></i>Weekly Metro Activity</h6>
                    <div class="green-streak-bar">${weekly.map(d => `<div class="streak-day ${d.active ? 'active' : 'inactive'}"><div>${d.day}</div>${d.active ? '<div>✓</div>' : ''}</div>`).join('')}</div>
                    <div style="margin-top:12px;font-size:12px;color:#94a3b8;text-align:center;">${data.green_streak > 0 ? '🔥 ' + data.green_streak + '-day green streak! Keep going!' : 'Take the metro today to start a streak!'}</div>
                </div>` : ''}
                <div class="glass-card mt-4" style="background:linear-gradient(135deg,rgba(5,150,105,0.04),rgba(52,211,153,0.02));">
                    <div class="d-flex align-items-center gap-3">
                        <div style="font-size:36px;">💡</div>
                        <div>
                            <div style="font-weight:800;font-size:15px;color:#059669;">Did you know?</div>
                            <div style="font-size:13px;color:#6b7280;">If every car commuter in Ahmedabad took metro once a week, we'd save <strong>2,400 tonnes</strong> of CO₂ annually.</div>
                        </div>
                    </div>
                </div>
            `;
        } catch (e) { console.log('Eco:', e); }
    }

    // ═══════════════════════════════════════════════════════════════
    //  JOURNEY PLANNER
    // ═══════════════════════════════════════════════════════════════
    async function loadJourneyPlanner() {
        // Populate station dropdowns
        try {
            const res = await fetch('/api/stations', { credentials: 'include' });
            const data = await res.json();
            if (!data.success) return;
            // Backend returns station names as strings; normalise to [{name}] objects
            const rawStations = data.stations || [];
            const stations = rawStations.map(s => typeof s === 'string' ? { name: s } : s);
            const srcSelect = document.getElementById('jpSource');
            const dstSelect = document.getElementById('jpDest');
            if (!srcSelect || !dstSelect) return;
            const options = '<option value="">Select station...</option>' + stations.map(s =>
                `<option value="${s.name}">${s.name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</option>`
            ).join('');
            srcSelect.innerHTML = options;
            dstSelect.innerHTML = options;
        } catch (e) { console.log('JP stations:', e); }
    }

    window.swapJPStations = function () {
        const src = document.getElementById('jpSource');
        const dst = document.getElementById('jpDest');
        if (src && dst) { const tmp = src.value; src.value = dst.value; dst.value = tmp; }
    };

    window.planJourney = async function () {
        const source = document.getElementById('jpSource')?.value;
        const dest = document.getElementById('jpDest')?.value;
        if (!source || !dest) { showToast('Select both stations', 'warning'); return; }
        if (source === dest) { showToast('Choose different stations', 'warning'); return; }

        const resultDiv = document.getElementById('jpResult');
        resultDiv.innerHTML = '<div class="glass-card text-center py-4"><i class="fas fa-spinner fa-spin me-2"></i>Finding best route...</div>';

        try {
            const res = await fetch('/api/journey/plan', {
                method: 'POST', credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source, destination: dest })
            });
            const data = await res.json();
            if (!data.success) { resultDiv.innerHTML = `<div class="glass-card"><div style="color:#ef4444;font-weight:700;"><i class="fas fa-exclamation-circle me-2"></i>${data.error}</div></div>`; return; }

            const route = data.route;
            const stationDots = route.map((s, i) => `
                <div class="jp-station ${i === 0 ? 'jp-start' : i === route.length - 1 ? 'jp-end' : ''}" style="animation-delay:${i * 0.12}s">
                    <div class="jp-dot"></div>
                    ${i < route.length - 1 ? '<div class="jp-line"></div>' : ''}
                    <div class="jp-name">${s.name}</div>
                </div>
            `).join('');

            resultDiv.innerHTML = `
                <div class="glass-card">
                    <div class="d-flex align-items-center gap-3 mb-4">
                        <div style="font-size:28px;">🗺️</div>
                        <div>
                            <h5 class="mb-1 fw-bold">${route[0].name} → ${route[route.length - 1].name}</h5>
                            <div style="font-size:12px;color:#94a3b8;"><i class="fas fa-microchip me-1"></i>${data.algorithm} • ${data.dataSource}</div>
                        </div>
                    </div>
                    <div class="jp-route-visual">${stationDots}</div>
                    <div class="row g-3 mt-4">
                        <div class="col-6 col-md-3"><div class="jp-info-card"><div class="jp-info-icon">🚉</div><div class="jp-info-num">${data.totalStops}</div><div class="jp-info-label">Stops</div></div></div>
                        <div class="col-6 col-md-3"><div class="jp-info-card"><div class="jp-info-icon">📏</div><div class="jp-info-num">${data.distanceKm} km</div><div class="jp-info-label">Distance</div></div></div>
                        <div class="col-6 col-md-3"><div class="jp-info-card"><div class="jp-info-icon">⏱️</div><div class="jp-info-num">${data.estimatedTimeMin} min</div><div class="jp-info-label">Est. Time</div></div></div>
                        <div class="col-6 col-md-3"><div class="jp-info-card"><div class="jp-info-icon">💰</div><div class="jp-info-num">₹${data.fare}</div><div class="jp-info-label">Fare</div></div></div>
                    </div>
                    ${data.interchanges > 0 ? '<div style="margin-top:16px;padding:12px 16px;background:rgba(245,158,11,0.08);border-radius:12px;font-size:13px;font-weight:600;"><i class="fas fa-exchange-alt me-2" style="color:#f59e0b;"></i>1 Interchange at Old High Court</div>' : ''}
                </div>
            `;
        } catch (e) { resultDiv.innerHTML = '<div class="glass-card" style="color:#ef4444;">Error planning journey</div>'; }
    };

    // ═══════════════════════════════════════════════════════════════
    //  TRAVEL STREAKS
    // ═══════════════════════════════════════════════════════════════
    async function loadStreaks() {
        try {
            const res = await fetch('/api/streaks', { credentials: 'include' });
            const data = await res.json();
            if (!data.success) return;
            const s = data.streaks;

            const container = document.getElementById('streaksContent');
            container.innerHTML = `
                <div class="row g-3 mb-4">
                    <div class="col-6 col-md-3">
                        <div class="streak-card streak-fire">
                            <div class="streak-icon">🔥</div>
                            <div class="streak-num">${s.currentStreak}</div>
                            <div class="streak-label">Current Streak</div>
                        </div>
                    </div>
                    <div class="col-6 col-md-3">
                        <div class="streak-card streak-best">
                            <div class="streak-icon">⚡</div>
                            <div class="streak-num">${s.longestStreak}</div>
                            <div class="streak-label">Longest Streak</div>
                        </div>
                    </div>
                    <div class="col-6 col-md-3">
                        <div class="streak-card">
                            <div class="streak-icon">📅</div>
                            <div class="streak-num">${s.totalTravelDays}</div>
                            <div class="streak-label">Travel Days</div>
                        </div>
                    </div>
                    <div class="col-6 col-md-3">
                        <div class="streak-card">
                            <div class="streak-icon">🗺️</div>
                            <div class="streak-num">${s.uniqueStations}</div>
                            <div class="streak-label">Stations</div>
                        </div>
                    </div>
                </div>
                <div class="glass-card">
                    <div class="d-flex align-items-center gap-2 mb-3">
                        <h5 class="mb-0 fw-bold"><i class="fas fa-medal me-2" style="color:#f59e0b;"></i>Milestones</h5>
                        <span style="background:linear-gradient(135deg,#f59e0b,#d97706);color:white;padding:4px 12px;border-radius:50px;font-size:11px;font-weight:800;">${s.unlockedCount}/${s.totalMilestones}</span>
                    </div>
                    <div class="milestone-grid">
                        ${s.milestones.map(m => {
                const pct = m.target > 0 ? Math.min(Math.round((m.current / m.target) * 100), 100) : 0;
                return `
                                <div class="milestone-card ${m.unlocked ? 'unlocked' : 'locked'}">
                                    <div class="milestone-icon">${m.icon}</div>
                                    <div class="milestone-name">${m.name}</div>
                                    <div class="milestone-progress-bar"><div class="milestone-progress-fill" style="width:${pct}%"></div></div>
                                    <div class="milestone-progress-text">${m.current}/${m.target} ${m.unlocked ? '✅' : ''}</div>
                                </div>
                            `;
            }).join('')}
                    </div>
                </div>
            `;
        } catch (e) { console.log('Streaks:', e); }
    }

    // Expose globally for inline onclick handlers
    window.loadFareComparison = window.loadFareComparison;
    window.toggleGroupMode = window.toggleGroupMode;
    window.addGroupPassenger = window.addGroupPassenger;
    window.removeGroupPassenger = window.removeGroupPassenger;
    window.saveBudget = window.saveBudget;
    window.planJourney = window.planJourney;
    window.swapJPStations = window.swapJPStations;
    // ═══════════════════════════════════════════════════════════════
    //  COMMAND PALETTE (Ctrl+K) — Linear/Notion inspired
    // ═══════════════════════════════════════════════════════════════
    (() => {
        const COMMANDS = [
            { icon: '🎫', label: 'Book Ticket', section: 'book-ticket', keys: 'book ticket metro' },
            { icon: '🎟️', label: 'My Tickets', section: 'tickets', keys: 'tickets history' },
            { icon: '💰', label: 'Wallet', section: 'wallet', keys: 'wallet balance recharge' },
            { icon: '💳', label: 'Metro Card', section: 'metro-card', keys: 'metro card nfc' },
            { icon: '📅', label: 'Monthly Pass', section: 'monthly-pass', keys: 'monthly pass subscription' },
            { icon: '👤', label: 'Profile', section: 'profile', keys: 'profile account user' },
            { icon: '🏆', label: 'Achievements', section: 'achievements', keys: 'achievements badges' },
            { icon: '📊', label: 'Spending', section: 'spending', keys: 'spending budget analytics' },
            { icon: '⚙️', label: 'Settings', section: 'settings', keys: 'settings preferences' },
            { icon: '🌿', label: 'Eco Impact', section: 'eco', keys: 'eco carbon green' },
            { icon: '🗺️', label: 'Journey Planner', section: 'journey-planner', keys: 'journey planner route' },
            { icon: '🔥', label: 'Travel Streaks', section: 'streaks', keys: 'streaks days' },
            { icon: '📋', label: 'Dashboard', section: 'dashboard', keys: 'dashboard home overview' },
        ];

        // Create palette DOM
        const overlay = document.createElement('div');
        overlay.id = 'cmdPaletteOverlay';
        overlay.style.cssText = `position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,0.5);backdrop-filter:blur(4px);display:none;align-items:flex-start;justify-content:center;padding-top:15vh;`;
        overlay.onclick = e => { if (e.target === overlay) closeCmdPalette(); };

        const modal = document.createElement('div');
        modal.id = 'cmdPaletteModal';
        modal.style.cssText = `background:white;border-radius:20px;width:520px;max-width:90vw;box-shadow:0 24px 80px rgba(0,0,0,0.25);overflow:hidden;animation:cmdSlideIn 0.2s ease;`;

        modal.innerHTML = `
            <div style="padding:18px 20px;border-bottom:1px solid #f1f5f9;display:flex;align-items:center;gap:12px;">
                <i class="fas fa-search" style="color:#94a3b8;font-size:15px;"></i>
                <input id="cmdPaletteInput" type="text" placeholder="Search commands..." style="border:none;outline:none;font-size:15px;font-weight:500;font-family:'Poppins',sans-serif;flex:1;color:#1e293b;" autocomplete="off">
                <kbd style="background:#f1f5f9;color:#94a3b8;padding:3px 8px;border-radius:6px;font-size:11px;font-weight:700;border:1px solid #e2e8f0;">ESC</kbd>
            </div>
            <div id="cmdPaletteList" style="max-height:340px;overflow-y:auto;padding:8px;"></div>
        `;
        overlay.appendChild(modal);
        document.body.appendChild(overlay);

        // CSS
        const cpStyle = document.createElement('style');
        cpStyle.textContent = `
            @keyframes cmdSlideIn{from{opacity:0;transform:translateY(-16px) scale(0.97)}to{opacity:1;transform:translateY(0) scale(1)}}
            .cmd-item{display:flex;align-items:center;gap:14px;padding:12px 16px;border-radius:12px;cursor:pointer;transition:all 0.15s;font-size:14px;font-weight:600;color:#334155;}
            .cmd-item:hover,.cmd-item.selected{background:linear-gradient(135deg,rgba(102,126,234,0.08),rgba(118,75,162,0.05));color:#667eea;}
            .cmd-item .cmd-icon{font-size:20px;width:36px;height:36px;display:flex;align-items:center;justify-content:center;background:rgba(102,126,234,0.06);border-radius:10px;}
            .cmd-item .cmd-shortcut{margin-left:auto;color:#cbd5e1;font-size:11px;font-weight:700;}
        `;
        document.head.appendChild(cpStyle);

        let selectedIdx = 0;
        let filteredCmds = [...COMMANDS];

        function renderCmds() {
            const list = document.getElementById('cmdPaletteList');
            if (!list) return;
            list.innerHTML = filteredCmds.length === 0
                ? `<div style="text-align:center;padding:32px;color:#94a3b8;font-size:13px;"><i class="fas fa-search" style="font-size:24px;display:block;margin-bottom:8px;opacity:0.3;"></i>No commands found</div>`
                : filteredCmds.map((c, i) => `
                    <div class="cmd-item ${i === selectedIdx ? 'selected' : ''}" data-idx="${i}" onmouseenter="window._cmdHover(${i})" onclick="window._cmdExec(${i})">
                        <span class="cmd-icon">${c.icon}</span>
                        <span>${c.label}</span>
                    </div>
                `).join('');
        }

        function openCmdPalette() {
            overlay.style.display = 'flex';
            const input = document.getElementById('cmdPaletteInput');
            if (input) { input.value = ''; input.focus(); }
            selectedIdx = 0;
            filteredCmds = [...COMMANDS];
            renderCmds();
        }

        function closeCmdPalette() {
            overlay.style.display = 'none';
        }

        window._cmdHover = i => { selectedIdx = i; renderCmds(); };
        window._cmdExec = i => {
            const cmd = filteredCmds[i];
            if (cmd && typeof showSection === 'function') {
                showSection(cmd.section);
            }
            closeCmdPalette();
        };

        // Keyboard shortcuts
        document.addEventListener('keydown', e => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                overlay.style.display === 'flex' ? closeCmdPalette() : openCmdPalette();
            }
            if (overlay.style.display === 'flex') {
                if (e.key === 'Escape') closeCmdPalette();
                if (e.key === 'ArrowDown') { e.preventDefault(); selectedIdx = (selectedIdx + 1) % filteredCmds.length; renderCmds(); }
                if (e.key === 'ArrowUp') { e.preventDefault(); selectedIdx = (selectedIdx - 1 + filteredCmds.length) % filteredCmds.length; renderCmds(); }
                if (e.key === 'Enter') { e.preventDefault(); window._cmdExec(selectedIdx); }
            }
        });

        // Search filtering
        document.addEventListener('input', e => {
            if (e.target.id !== 'cmdPaletteInput') return;
            const q = e.target.value.toLowerCase().trim();
            filteredCmds = q ? COMMANDS.filter(c => (c.label + ' ' + c.keys).toLowerCase().includes(q)) : [...COMMANDS];
            selectedIdx = 0;
            renderCmds();
        });
    })();

    // ═══════════════════════════════════════════════════════════════
    //  NEXT TRAIN COUNTDOWN WIDGET — disabled (HTML already has #nextTrainCard)
    // ═══════════════════════════════════════════════════════════════
    (() => {
        // Intentionally skipped: the dashboard HTML has a built-in
        // #nextTrainCard with live countdown. Injecting a second widget
        // caused visual overlap and layout glitches.
        return;
        widget.style.cssText = `
            background:linear-gradient(135deg,rgba(102,126,234,0.06),rgba(118,75,162,0.04));
            border:1px solid rgba(102,126,234,0.1);border-radius:20px;padding:20px 24px;
            display:flex;align-items:center;gap:20px;margin-bottom:20px;
            animation:fadeIn 0.5s ease;
        `;
        widget.innerHTML = `
            <div style="position:relative;width:64px;height:64px;flex-shrink:0;">
                <svg viewBox="0 0 64 64" style="width:64px;height:64px;transform:rotate(-90deg);">
                    <circle cx="32" cy="32" r="28" fill="none" stroke="rgba(102,126,234,0.1)" stroke-width="5"/>
                    <circle id="trainCountdownRing" cx="32" cy="32" r="28" fill="none" stroke="url(#trainGrad)" stroke-width="5" stroke-linecap="round" stroke-dasharray="175.9" stroke-dashoffset="0" style="transition:stroke-dashoffset 1s linear;"/>
                    <defs><linearGradient id="trainGrad" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#667eea"/><stop offset="100%" stop-color="#764ba2"/></linearGradient></defs>
                </svg>
                <div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:20px;">🚇</div>
            </div>
            <div style="flex:1;">
                <div style="font-size:12px;font-weight:800;color:#94a3b8;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">Next Train</div>
                <div style="display:flex;align-items:baseline;gap:6px;">
                    <span id="trainCountdownMin" style="font-size:32px;font-weight:900;background:linear-gradient(135deg,#667eea,#764ba2);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">0</span>
                    <span style="font-size:14px;font-weight:600;color:#94a3b8;">min</span>
                    <span id="trainCountdownSec" style="font-size:20px;font-weight:800;color:#64748b;">00</span>
                    <span style="font-size:12px;font-weight:600;color:#94a3b8;">sec</span>
                </div>
                <div style="font-size:11px;color:#94a3b8;margin-top:2px;" id="trainPlatformText">Platform info loading...</div>
            </div>
            <div style="text-align:right;">
                <div style="width:8px;height:8px;background:#22c55e;border-radius:50%;display:inline-block;animation:pulse-ring 2s infinite;"></div>
                <span style="font-size:11px;font-weight:700;color:#22c55e;margin-left:4px;">ON TIME</span>
            </div>
        `;

        // Insert near top of dashboard (safely — avoid "not a child" error)
        const firstChild = dashSection.querySelector(':scope > .row, :scope > .glass-card, :scope > h2, :scope > #smartGreetingBanner');
        if (firstChild && firstChild.parentNode === dashSection) {
            dashSection.insertBefore(widget, firstChild.nextSibling);
        } else {
            dashSection.prepend(widget);
        }

        // Countdown logic — simulate random interval 2–8 min
        let totalSec = Math.floor(Math.random() * 360) + 120; // 2-8 min
        const TOTAL = totalSec;

        function updateCountdown() {
            const min = Math.floor(totalSec / 60);
            const sec = totalSec % 60;
            const minEl = document.getElementById('trainCountdownMin');
            const secEl = document.getElementById('trainCountdownSec');
            const ring = document.getElementById('trainCountdownRing');
            if (minEl) minEl.textContent = min;
            if (secEl) secEl.textContent = sec.toString().padStart(2, '0');
            if (ring) ring.style.strokeDashoffset = 175.9 * (1 - totalSec / TOTAL);

            totalSec--;
            if (totalSec < 0) {
                totalSec = Math.floor(Math.random() * 360) + 120;
                const platEl = document.getElementById('trainPlatformText');
                if (platEl) platEl.textContent = `Platform ${Math.ceil(Math.random() * 4)} · Blue Line`;
            }
        }

        document.getElementById('trainPlatformText').textContent = `Platform ${Math.ceil(Math.random() * 4)} · ${Math.random() > 0.5 ? 'Blue' : 'Green'} Line`;
        updateCountdown();
        setInterval(updateCountdown, 1000);
    })();

    // ═══════════════════════════════════════════════════════════════
    //  TIME-AWARE GREETING BANNER
    // ═══════════════════════════════════════════════════════════════
    (() => {
        const banner = document.getElementById('smartGreetingBanner');
        if (!banner) return;

        const hr = new Date().getHours();
        let gradient, greeting, tip, emoji;

        if (hr >= 5 && hr < 8) {
            gradient = 'linear-gradient(135deg, #ffecd2, #fcb69f)';
            greeting = 'Good Morning';
            emoji = '🌅';
            tip = 'Early bird catches the best seats! Off-peak fares are active now.';
        } else if (hr >= 8 && hr < 12) {
            gradient = 'linear-gradient(135deg, #a1c4fd, #c2e9fb)';
            greeting = 'Good Morning';
            emoji = '☀️';
            tip = 'Peak hours until 10 AM — consider express routes for faster commute.';
        } else if (hr >= 12 && hr < 17) {
            gradient = 'linear-gradient(135deg, #89f7fe, #66a6ff)';
            greeting = 'Good Afternoon';
            emoji = '🌤️';
            tip = 'Midday travel is smooth. Great time to plan your evening return.';
        } else if (hr >= 17 && hr < 20) {
            gradient = 'linear-gradient(135deg, #fbc2eb, #a6c1ee)';
            greeting = 'Good Evening';
            emoji = '🌆';
            tip = 'Evening rush starting — book ahead to skip the queue!';
        } else {
            gradient = 'linear-gradient(135deg, #2b5876, #4e4376)';
            greeting = 'Good Night';
            emoji = '🌙';
            tip = 'Late night services run every 15 min. Last train at 11 PM.';
        }

        banner.style.background = gradient;
        banner.style.borderRadius = '20px';
        banner.style.padding = '20px 28px';
        banner.style.marginBottom = '20px';
        banner.style.color = hr >= 20 || hr < 5 ? 'white' : '#1e293b';
        banner.style.position = 'relative';
        banner.style.overflow = 'hidden';

        // Update text
        const h2 = banner.querySelector('h2, h3, h4');
        if (h2) {
            const username = h2.textContent.replace(/.*,\s*/, '').replace(/[!.].*/, '').trim();
            h2.innerHTML = `${emoji} ${greeting}, ${username || 'Commuter'}!`;
        }

        // Add commuter tip
        let tipEl = banner.querySelector('.commuter-tip');
        if (!tipEl) {
            tipEl = document.createElement('div');
            tipEl.className = 'commuter-tip';
            tipEl.style.cssText = 'font-size:12px;opacity:0.8;margin-top:8px;display:flex;align-items:center;gap:8px;';
            banner.appendChild(tipEl);
        }
        tipEl.innerHTML = `<i class="fas fa-lightbulb" style="font-size:14px;"></i> <span>${tip}</span>`;
    })();

    // ═══════════════════════════════════════════════════════════════
    //  ROUND 3 — FEATURE 1: SMOOTH PAGE TRANSITION LOADER
    // ═══════════════════════════════════════════════════════════════
    (() => {
        // Create overlay element
        const overlay = document.createElement('div');
        overlay.className = 'section-transition-overlay';
        overlay.innerHTML = `
            <div class="transition-train-icon">🚇</div>
            <div class="transition-skeleton">
                <div class="skel-line"></div>
                <div class="skel-line"></div>
                <div class="skel-line"></div>
                <div class="skel-line"></div>
            </div>
        `;
        document.body.appendChild(overlay);

        // Wrap showSection to add transition
        const origShow = window.showSection;
        if (typeof origShow === 'function') {
            window.showSection = function(section) {
                overlay.classList.add('active');
                setTimeout(() => {
                    origShow(section);
                    setTimeout(() => {
                        overlay.classList.remove('active');
                    }, 300);
                }, 350);
            };
        }
    })();

    // ═══════════════════════════════════════════════════════════════
    //  ROUND 3 — FEATURE 3: FLOATING QUICK ACTIONS FAB
    // ═══════════════════════════════════════════════════════════════
    (() => {
        if (!document.querySelector('.main-content')) return;

        const fabActions = [
            { icon: 'fa-ticket-alt', label: 'Book Ticket', color: '#667eea', section: 'book-ticket' },
            { icon: 'fa-wallet', label: 'Top Up Wallet', color: '#22c55e', section: 'wallet' },
            { icon: 'fa-qrcode', label: 'My Tickets', color: '#f59e0b', section: 'my-tickets' },
            { icon: 'fa-headset', label: 'Get Support', color: '#ef4444', section: 'feedback' },
        ];

        const container = document.createElement('div');
        container.className = 'mf-fab-container';
        container.innerHTML = `
            <button class="mf-fab-main" id="fabMainBtn" title="Quick Actions">
                <i class="fas fa-plus"></i>
            </button>
            <div class="mf-fab-menu" id="fabMenu">
                ${fabActions.map(a => `
                    <div class="mf-fab-item" data-section="${a.section}">
                        <span class="mf-fab-label">${a.label}</span>
                        <button class="mf-fab-btn" style="background:${a.color}">
                            <i class="fas ${a.icon}"></i>
                        </button>
                    </div>
                `).join('')}
            </div>
        `;
        document.body.appendChild(container);

        const mainBtn = document.getElementById('fabMainBtn');
        const menu = document.getElementById('fabMenu');
        let isOpen = false;

        mainBtn.addEventListener('click', () => {
            isOpen = !isOpen;
            mainBtn.classList.toggle('open', isOpen);
            menu.classList.toggle('open', isOpen);
        });

        menu.querySelectorAll('.mf-fab-item').forEach(item => {
            item.addEventListener('click', () => {
                const section = item.dataset.section;
                if (typeof window.showSection === 'function') {
                    window.showSection(section);
                }
                isOpen = false;
                mainBtn.classList.remove('open');
                menu.classList.remove('open');
            });
        });

        // Close on outside click
        document.addEventListener('click', e => {
            if (isOpen && !container.contains(e.target)) {
                isOpen = false;
                mainBtn.classList.remove('open');
                menu.classList.remove('open');
            }
        });
    })();

    // ═══════════════════════════════════════════════════════════════
    //  ROUND 3 — FEATURE 4: ANIMATED NUMBER COUNTERS
    // ═══════════════════════════════════════════════════════════════
    (() => {
        function animateCounter(el, target, duration = 1200, prefix = '', suffix = '') {
            const start = 0;
            const startTime = performance.now();

            function easeOutExpo(t) {
                return t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
            }

            function update(now) {
                const elapsed = now - startTime;
                const progress = Math.min(elapsed / duration, 1);
                const easedProgress = easeOutExpo(progress);
                const current = Math.round(start + (target - start) * easedProgress);
                el.textContent = prefix + current.toLocaleString() + suffix;
                if (progress < 1) {
                    requestAnimationFrame(update);
                } else {
                    el.classList.add('counter-flash');
                    setTimeout(() => el.classList.remove('counter-flash'), 600);
                }
            }
            requestAnimationFrame(update);
        }

        // Observe dashboard stat elements for visibility
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting && !entry.target._counted) {
                    entry.target._counted = true;
                    const text = entry.target.textContent.trim();
                    const prefix = text.match(/^[₹$€£]/)?.[0] || '';
                    const suffix = text.match(/[%+kK]$/)?.[0] || '';
                    const num = parseFloat(text.replace(/[^0-9.]/g, ''));
                    if (!isNaN(num) && num > 0) {
                        animateCounter(entry.target, num, 1500, prefix, suffix);
                    }
                }
            });
        }, { threshold: 0.3 });

        // Watch for stat cards appearing
        setTimeout(() => {
            document.querySelectorAll('.stat-value, .stat-card-modern h3, [id^="dashboard"]').forEach(el => {
                const text = el.textContent.trim();
                const num = parseFloat(text.replace(/[^0-9.]/g, ''));
                if (!isNaN(num) && num > 0 && text.length < 15) {
                    observer.observe(el);
                }
            });
        }, 2000);
    })();

    // ═══════════════════════════════════════════════════════════════
    //  ROUND 3 — FEATURE 5: TOAST NOTIFICATION SYSTEM
    // ═══════════════════════════════════════════════════════════════
    (() => {
        // Create container
        let toastContainer = document.querySelector('.mf-toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.className = 'mf-toast-container';
            document.body.appendChild(toastContainer);
        }

        const ICONS = {
            success: 'fa-check-circle',
            error: 'fa-times-circle',
            warning: 'fa-exclamation-triangle',
            info: 'fa-info-circle'
        };

        window.mfToast = function(message, type = 'info', duration = 4000) {
            const toast = document.createElement('div');
            toast.className = 'mf-toast';
            toast.innerHTML = `
                <div class="mf-toast-icon ${type}"><i class="fas ${ICONS[type] || ICONS.info}"></i></div>
                <span class="mf-toast-text">${message}</span>
                <button class="mf-toast-close" onclick="this.parentElement.classList.add('removing');setTimeout(()=>this.parentElement.remove(),300)">
                    <i class="fas fa-times"></i>
                </button>
                <div class="mf-toast-progress ${type}" style="width:100%;transition:width ${duration}ms linear"></div>
            `;
            toastContainer.appendChild(toast);

            // Animate progress bar
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    toast.querySelector('.mf-toast-progress').style.width = '0%';
                });
            });

            // Auto-remove
            setTimeout(() => {
                if (toast.parentElement) {
                    toast.classList.add('removing');
                    setTimeout(() => toast.remove(), 300);
                }
            }, duration);

            // Max 5 toasts
            while (toastContainer.children.length > 5) {
                toastContainer.firstElementChild.remove();
            }
        };

        // Show welcome toast after a delay
        setTimeout(() => {
            if (document.querySelector('.main-content')) {
                window.mfToast('Welcome back! 🚇 Your dashboard is ready.', 'success', 3000);
            }
        }, 3000);
    })();

    // ═══════════════════════════════════════════════════════════════
    //  ROUND 3 — FEATURE 6: ENHANCED DARK MODE TOGGLE
    // ═══════════════════════════════════════════════════════════════
    (() => {
        const sidebar = document.querySelector('.sidebar');
        if (!sidebar) return;

        // Find logout link to insert before it
        const logoutLink = sidebar.querySelector('.sidebar-link.text-danger') || sidebar.lastElementChild;

        const toggle = document.createElement('div');
        toggle.className = 'mf-theme-toggle';
        toggle.id = 'mfThemeToggle';

        const isDark = document.body.classList.contains('dark-mode') || localStorage.getItem('mf-dark-mode') === 'true';
        toggle.innerHTML = `
            <div class="mf-theme-icon ${isDark ? 'moon' : 'sun'}" id="themeIconEl">${isDark ? '🌙' : '☀️'}</div>
            <span class="mf-theme-label" id="themeLabelEl">${isDark ? 'Dark Mode' : 'Light Mode'}</span>
        `;

        if (logoutLink) sidebar.insertBefore(toggle, logoutLink);
        else sidebar.appendChild(toggle);

        // Apply saved preference
        if (isDark) document.body.classList.add('dark-mode');

        toggle.addEventListener('click', () => {
            const nowDark = !document.body.classList.contains('dark-mode');
            document.body.classList.toggle('dark-mode', nowDark);
            localStorage.setItem('mf-dark-mode', nowDark);

            const iconEl = document.getElementById('themeIconEl');
            const labelEl = document.getElementById('themeLabelEl');
            if (iconEl) {
                iconEl.className = `mf-theme-icon ${nowDark ? 'moon' : 'sun'}`;
                iconEl.textContent = nowDark ? '🌙' : '☀️';
            }
            if (labelEl) labelEl.textContent = nowDark ? 'Dark Mode' : 'Light Mode';

            // Smooth transition effect
            document.body.style.transition = 'background 0.5s ease, color 0.5s ease';
            setTimeout(() => { document.body.style.transition = ''; }, 600);

            window.mfToast?.(`Switched to ${nowDark ? 'Dark' : 'Light'} Mode ${nowDark ? '🌙' : '☀️'}`, 'info', 2000);
        });
    })();

    // ═══════════════════════════════════════════════════════════════
    //  ROUND 3 — FEATURE 7: AMBIENT TYPING SOUNDS
    // ═══════════════════════════════════════════════════════════════
    (() => {
        // Only on desktop
        if (window.innerWidth < 768) return;

        // Create audio context lazily
        let audioCtx = null;
        function playKeyClick() {
            try {
                if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                const osc = audioCtx.createOscillator();
                const gain = audioCtx.createGain();
                osc.connect(gain);
                gain.connect(audioCtx.destination);
                osc.frequency.value = 800 + Math.random() * 400;
                osc.type = 'sine';
                gain.gain.value = 0.015;
                gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.06);
                osc.start(audioCtx.currentTime);
                osc.stop(audioCtx.currentTime + 0.06);
            } catch(e) { /* audio not available */ }
        }

        let soundEnabled = localStorage.getItem('mf-typing-sounds') !== 'false';
        document.addEventListener('keydown', e => {
            if (!soundEnabled) return;
            const tag = e.target.tagName;
            if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
                if (e.key.length === 1 || e.key === 'Backspace' || e.key === 'Enter') {
                    playKeyClick();
                }
            }
        });
    })();

    // ═══════════════════════════════════════════════════════════════
    //  ROUND 3 — FEATURE 8: CONFETTI CELEBRATION
    // ═══════════════════════════════════════════════════════════════
    (() => {
        window.mfConfetti = function(duration = 2500) {
            const canvas = document.createElement('canvas');
            canvas.className = 'confetti-canvas';
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
            document.body.appendChild(canvas);
            const ctx = canvas.getContext('2d');

            const COLORS = ['#667eea', '#764ba2', '#f093fb', '#f5576c', '#22c55e', '#f59e0b', '#00f2fe', '#fbbf24'];
            const particles = [];

            for (let i = 0; i < 120; i++) {
                particles.push({
                    x: Math.random() * canvas.width,
                    y: Math.random() * canvas.height * -0.5,
                    w: Math.random() * 10 + 4,
                    h: Math.random() * 6 + 2,
                    color: COLORS[Math.floor(Math.random() * COLORS.length)],
                    vx: (Math.random() - 0.5) * 6,
                    vy: Math.random() * 3 + 2,
                    rot: Math.random() * 360,
                    rotV: (Math.random() - 0.5) * 12,
                    gravity: 0.08 + Math.random() * 0.04,
                    opacity: 1,
                    decay: 0.003 + Math.random() * 0.005
                });
            }

            const startTime = Date.now();
            function draw() {
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                const elapsed = Date.now() - startTime;
                let alive = false;

                particles.forEach(p => {
                    if (p.opacity <= 0) return;
                    alive = true;
                    p.x += p.vx;
                    p.vy += p.gravity;
                    p.y += p.vy;
                    p.rot += p.rotV;
                    p.vx *= 0.99;
                    if (elapsed > duration * 0.6) p.opacity -= p.decay * 2;

                    ctx.save();
                    ctx.translate(p.x, p.y);
                    ctx.rotate(p.rot * Math.PI / 180);
                    ctx.globalAlpha = Math.max(0, p.opacity);
                    ctx.fillStyle = p.color;
                    ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
                    ctx.restore();
                });

                if (alive && elapsed < duration) {
                    requestAnimationFrame(draw);
                } else {
                    canvas.remove();
                }
            }
            requestAnimationFrame(draw);
        };

        // Hook into booking confirmation
        const origClose = window.closeBookingConfirm;
        if (typeof origClose !== 'function') {
            // Watch for the booking confirm overlay appearing
            const mo = new MutationObserver(() => {
                const overlay = document.getElementById('bookingConfirmOverlay');
                if (overlay && overlay.style.display !== 'none' && !overlay._confettiFired) {
                    overlay._confettiFired = true;
                    window.mfConfetti(3000);
                    window.mfToast?.('🎉 Ticket booked successfully!', 'success', 3500);
                    setTimeout(() => { overlay._confettiFired = false; }, 5000);
                }
            });
            const overlay = document.getElementById('bookingConfirmOverlay');
            if (overlay) mo.observe(overlay, { attributes: true, attributeFilter: ['style'] });
        }
    })();

})();

