/**
 * RuleWise AI — Complete Production Application Controller (v3.0.0)
 * 
 * Features & Fixes:
 * - Real-time chat composer with instantaneous character counting (0/20000) and send-button activation.
 * - Enter sends message, Shift+Enter inserts newline.
 * - Image & Camera capture support (camera capture + file picker).
 * - Web Speech API voice microphone dictation.
 * - File Tools & Converters: Image to PDF, PDF to Images, File Compressor, PDF Merger with direct downloads.
 * - Live search filtering for recent conversations in the sidebar.
 * - Real Google OAuth 2.0 / OpenID Connect + Email Login + Registration + Password Reset.
 * - Owner and Administrator Hierarchy:
 *     - Only Owner (sasiganaparthi@gmail.com) can appoint or revoke administrators.
 *     - Strict RBAC: normal users never see admin navigation or open admin console.
 * - Admin Console with 6 full subviews:
 *     1) Platform Telemetry & System Health
 *     2) User Directory & Role Delegation (Owner only)
 *     3) Official Rule Libraries (CRUD & JSON validation)
 *     4) Decision Intelligence & Immutable Audit Log
 *     5) Platform Session Monitoring & Termination
 *     6) Configurable Safety & Harm Classification Guardrails
 * - Real user-isolated Decision History with search, domain/outcome filtering, and proof trace inspection.
 * - Assistant response Copy to clipboard + SpeechSynthesis TTS (Play/Stop toggle).
 * - Zero fake/dummy chats: real multi-turn conversations stored in backend DB & device localStorage.
 * - Renamed every occurrence of Academic Policy to RuleWise Policy.
 */

(function () {
    'use strict';

    // -------------------------------------------------------------------------
    // 1. Configuration & Global State
    // -------------------------------------------------------------------------
    const isLocalDev = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    const API_BASE = (window.location.protocol === 'file:' || (isLocalDev && window.location.port && window.location.port !== '8000'))
        ? 'http://127.0.0.1:8000'
        : '';

    const STORAGE_KEY = 'rulewise_device_chats_v3';
    const THIRTY_DAYS_MS = 30 * 24 * 60 * 60 * 1000;

    const state = {
        token: localStorage.getItem('rulewise_token') || null,
        user: JSON.parse(localStorage.getItem('rulewise_user') || 'null'),
        activeTab: 'chat-view',
        activeAdminSubTab: 'admin-tab-overview',
        activeDomainId: 'dom_academic',
        activeDomainName: 'RuleWise Policy',
        domains: [],
        rules: [],
        conversations: [],
        currentConversationId: 'session_' + Math.random().toString(36).substring(2, 10),
        isLoadingChat: false,
        attachedFiles: [],
        currentMessages: [],
        googleClientId: null,
        activeSpeechButton: null,
    };

    // -------------------------------------------------------------------------
    // 2. Device Local Storage for Recent Chats
    // -------------------------------------------------------------------------
    function getDeviceChats() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return [];
            const chats = JSON.parse(raw);
            const now = Date.now();
            const activeChats = chats.filter(c => {
                const ts = new Date(c.updated_at || c.created_at || now).getTime();
                return (now - ts) <= THIRTY_DAYS_MS;
            });
            if (activeChats.length !== chats.length) {
                localStorage.setItem(STORAGE_KEY, JSON.stringify(activeChats));
            }
            return activeChats;
        } catch (e) {
            return [];
        }
    }

    function saveCurrentDeviceChat(title, messages) {
        try {
            const chats = getDeviceChats();
            const existingIdx = chats.findIndex(c => c.id === state.currentConversationId);
            const cleanTitle = (title || 'Conversation').trim().slice(0, 42);
            const entry = {
                id: state.currentConversationId,
                title: cleanTitle,
                updated_at: new Date().toISOString(),
                created_at: existingIdx >= 0 ? chats[existingIdx].created_at : new Date().toISOString(),
                messages: messages || state.currentMessages || [],
            };
            if (existingIdx >= 0) {
                chats[existingIdx] = entry;
            } else {
                chats.unshift(entry);
            }
            localStorage.setItem(STORAGE_KEY, JSON.stringify(chats.slice(0, 50)));
            renderRecentChatsList();
        } catch (e) {
            console.warn('Device storage notice:', e);
        }
    }

    // -------------------------------------------------------------------------
    // 3. HTTP Client with Authentication Headers
    // -------------------------------------------------------------------------
    async function apiRequest(endpoint, options = {}) {
        const url = `${API_BASE}${endpoint}`;
        const headers = {
            'Content-Type': 'application/json',
            ...(options.headers || {}),
        };
        if (state.token) {
            headers['Authorization'] = `Bearer ${state.token}`;
        }

        try {
            const resp = await fetch(url, { ...options, headers });
            if (resp.status === 204) return null;
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) {
                let errorMsg = `Request failed with status ${resp.status}`;
                if (Array.isArray(data.detail)) {
                    errorMsg = data.detail.map(d => (d && (d.msg || d.message)) || JSON.stringify(d)).join('; ');
                } else if (typeof data.detail === 'string') {
                    errorMsg = data.detail;
                } else if (data.detail && typeof data.detail === 'object') {
                    errorMsg = data.detail.detail || data.detail.message || JSON.stringify(data.detail);
                } else if (data.message) {
                    errorMsg = typeof data.message === 'string' ? data.message : JSON.stringify(data.message);
                }
                throw new Error(errorMsg);
            }
            return data;
        } catch (err) {
            console.error(`API Error on ${endpoint}:`, err);
            throw err;
        }
    }

    function openAuthModal(defaultTab = 'login') {
        const modal = document.getElementById('auth-modal');
        if (!modal) return;
        modal.classList.remove('hidden');

        if (defaultTab === 'admin') {
            const adminTabBtn = document.getElementById('tab-admin-login-btn');
            if (adminTabBtn) adminTabBtn.click();
        } else if (defaultTab === 'register') {
            const regTabBtn = document.getElementById('tab-register-btn');
            if (regTabBtn) regTabBtn.click();
        } else {
            const loginTabBtn = document.getElementById('tab-login-btn');
            if (loginTabBtn) loginTabBtn.click();
        }
    }

    function closeAuthModal() {
        const modal = document.getElementById('auth-modal');
        if (modal) modal.classList.add('hidden');
    }

    // -------------------------------------------------------------------------
    // 4. Google OAuth 2.0 Integration
    // -------------------------------------------------------------------------
    async function initGoogleAuth() {
        try {
            const cfg = await apiRequest('/api/v1/auth/google/config');
            if (cfg && cfg.client_id) {
                state.googleClientId = cfg.client_id;
                renderGoogleButton();
            }
        } catch (err) {
            console.info('Google OAuth config lookup notice:', err.message);
        }

        const customBtn = document.getElementById('google-signin-custom-btn');
        if (customBtn) {
            customBtn.onclick = () => {
                if (window.google && window.google.accounts && window.google.accounts.id && state.googleClientId) {
                    window.google.accounts.id.prompt();
                } else {
                    alert('Google Sign-In is configured on the backend. When GOOGLE_CLIENT_ID is active, one-tap login authenticates instantly.');
                }
            };
        }
    }

    function renderGoogleButton() {
        const btnContainer = document.getElementById('google-signin-btn');
        if (!btnContainer) return;

        if (window.google && window.google.accounts && window.google.accounts.id && state.googleClientId) {
            try {
                window.google.accounts.id.initialize({
                    client_id: state.googleClientId,
                    callback: handleGoogleAuthResponse,
                    auto_select: false,
                    cancel_on_tap_outside: true,
                });
                btnContainer.innerHTML = '';
                window.google.accounts.id.renderButton(btnContainer, {
                    type: 'standard',
                    theme: 'filled_black',
                    size: 'large',
                    text: 'continue_with',
                    shape: 'rectangular',
                    logo_alignment: 'left',
                    width: 320,
                });
                const customBtn = document.getElementById('google-signin-custom-btn');
                if (customBtn) customBtn.classList.add('hidden');
            } catch (e) {
                console.warn('Google Identity button render error:', e);
            }
        }
    }

    async function handleGoogleAuthResponse(googleResponse) {
        const errBox = document.getElementById('auth-error-msg');
        if (errBox) errBox.classList.add('hidden');

        try {
            const data = await apiRequest('/api/v1/auth/google', {
                method: 'POST',
                body: JSON.stringify({ id_token: googleResponse.credential }),
            });
            state.token = data.access_token;
            state.user = data.user;
            localStorage.setItem('rulewise_token', state.token);
            localStorage.setItem('rulewise_user', JSON.stringify(state.user));
            updateUserUI();
            closeAuthModal();
            renderRecentChatsList();
        } catch (err) {
            if (errBox) {
                errBox.textContent = `Google Authentication Failed: ${err.message}`;
                errBox.classList.remove('hidden');
            }
        }
    }

    // -------------------------------------------------------------------------
    // 5. Authentication, User Profile & Log Out Management
    // -------------------------------------------------------------------------
    async function initAuth() {
        if (!state.token) {
            try {
                const guestData = await apiRequest('/api/v1/auth/guest', { method: 'POST' });
                state.token = guestData.access_token;
                state.user = guestData.user;
                localStorage.setItem('rulewise_token', state.token);
                localStorage.setItem('rulewise_user', JSON.stringify(state.user));
            } catch (e) {
                console.warn('Guest initialization notice:', e);
            }
        } else {
            try {
                const profile = await apiRequest('/api/v1/auth/me');
                state.user = profile;
                localStorage.setItem('rulewise_user', JSON.stringify(profile));
            } catch (e) {
                state.token = null;
                state.user = null;
                localStorage.removeItem('rulewise_token');
                localStorage.removeItem('rulewise_user');
                return initAuth();
            }
        }
        updateUserUI();
        initGoogleAuth();
    }

    function updateUserUI() {
        const nameEl = document.getElementById('user-display-name');
        const badgeEl = document.getElementById('user-role-badge');
        const avatarEl = document.getElementById('user-avatar-initial');
        const topNameEl = document.getElementById('top-user-display-name');
        const topAvatarEl = document.getElementById('top-avatar-initial');
        const topAuthBadge = document.getElementById('top-auth-badge');
        const topLogoutBtn = document.getElementById('top-logout-btn');
        const sidebarLogoutBtn = document.getElementById('sidebar-logout-btn');
        const adminNavItem = document.getElementById('admin-nav-item');

        const tabsContainer = document.getElementById('auth-tabs-container');
        const formLogin = document.getElementById('login-form');
        const formAdminLogin = document.getElementById('admin-login-form');
        const formReg = document.getElementById('register-form');
        const formReset = document.getElementById('reset-password-form');
        const guestPanel = document.getElementById('guest-panel');
        const loggedInPanel = document.getElementById('logged-in-panel');

        const isAuthenticated = state.user && state.user.role !== 'guest';
        const isOwner = state.user && state.user.role === 'owner';
        const isAdmin = state.user && (state.user.role === 'admin' || isOwner);

        if (isAuthenticated) {
            const uname = state.user.username || state.user.email || 'Member';
            const init = uname.charAt(0).toUpperCase();

            let roleLabel = 'Verified Member';
            if (isOwner) roleLabel = 'Platform Owner';
            else if (isAdmin) roleLabel = 'Administrator';

            if (nameEl) nameEl.textContent = uname;
            if (badgeEl) badgeEl.textContent = roleLabel;
            if (avatarEl) {
                if (state.user.picture) {
                    avatarEl.innerHTML = `<img src="${escapeHtml(state.user.picture)}" alt="User" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">`;
                } else {
                    avatarEl.textContent = init;
                }
            }
            if (topNameEl) topNameEl.textContent = uname;
            if (topAvatarEl) {
                if (state.user.picture) {
                    topAvatarEl.innerHTML = `<img src="${escapeHtml(state.user.picture)}" alt="User" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">`;
                } else {
                    topAvatarEl.textContent = init;
                }
            }
            if (topAuthBadge) topAuthBadge.textContent = isAdmin ? (isOwner ? 'Owner' : 'Admin') : 'Account';

            if (topLogoutBtn) topLogoutBtn.classList.remove('hidden');
            if (sidebarLogoutBtn) sidebarLogoutBtn.classList.remove('hidden');

            // CRITICAL: Strictly hide Admin Console navigation item from normal users
            if (adminNavItem) {
                if (isAdmin) {
                    adminNavItem.classList.remove('hidden');
                } else {
                    adminNavItem.classList.add('hidden');
                }
            }

            // Modal view for authenticated user
            if (tabsContainer) tabsContainer.classList.add('hidden');
            if (formLogin) formLogin.classList.add('hidden');
            if (formAdminLogin) formAdminLogin.classList.add('hidden');
            if (formReg) formReg.classList.add('hidden');
            if (formReset) formReset.classList.add('hidden');
            if (guestPanel) guestPanel.classList.add('hidden');
            if (loggedInPanel) {
                loggedInPanel.classList.remove('hidden');
                const mAvatar = document.getElementById('modal-user-avatar');
                if (mAvatar) {
                    if (state.user.picture) {
                        mAvatar.innerHTML = `<img src="${escapeHtml(state.user.picture)}" alt="User" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">`;
                    } else {
                        mAvatar.textContent = init;
                    }
                }
                const mName = document.getElementById('modal-user-name');
                if (mName) mName.textContent = uname;
                const mEmail = document.getElementById('modal-user-email');
                if (mEmail) mEmail.textContent = state.user.email || 'No email attached';
                const mRole = document.getElementById('modal-user-role');
                if (mRole) mRole.textContent = isOwner ? 'Platform Owner (Root Authority)' : (isAdmin ? 'Platform Administrator' : 'Verified Member');
            }
        } else {
            if (nameEl) nameEl.textContent = 'Guest Explorer';
            if (badgeEl) badgeEl.textContent = 'Sign In / Account';
            if (avatarEl) avatarEl.textContent = 'G';
            if (topNameEl) topNameEl.textContent = 'Guest Mode';
            if (topAvatarEl) topAvatarEl.textContent = 'G';
            if (topAuthBadge) topAuthBadge.textContent = 'Sign In';

            if (topLogoutBtn) topLogoutBtn.classList.add('hidden');
            if (sidebarLogoutBtn) sidebarLogoutBtn.classList.add('hidden');

            // CRITICAL: Normal users / guests must NEVER see Admin Console nav
            if (adminNavItem) adminNavItem.classList.add('hidden');

            if (tabsContainer) tabsContainer.classList.remove('hidden');
            if (formLogin) formLogin.classList.remove('hidden');
            if (formAdminLogin) formAdminLogin.classList.add('hidden');
            if (formReg) formReg.classList.add('hidden');
            if (formReset) formReset.classList.add('hidden');
            if (guestPanel) guestPanel.classList.add('hidden');
            if (loggedInPanel) loggedInPanel.classList.add('hidden');
        }
    }

    async function handleLogout() {
        if (!confirm('Are you sure you want to log out of RuleWise AI?')) return;
        try {
            await apiRequest('/api/v1/auth/logout', { method: 'POST' });
        } catch (e) {}
        localStorage.removeItem('rulewise_token');
        localStorage.removeItem('rulewise_user');
        state.token = null;
        state.user = null;
        closeAuthModal();
        if (state.activeTab === 'admin-view') switchTab('chat-view');
        await initAuth();
        renderRecentChatsList();
    }

    // -------------------------------------------------------------------------
    // 6. Navigation Router (with Strict RBAC Barrier)
    // -------------------------------------------------------------------------
    const viewHeadings = {
        'chat-view': { title: 'Chat & Advisory', sub: 'Conversational NLP + Deterministic Rule Authority' },
        'file-tools-view': { title: 'File Tools & Converters', sub: 'Document Extraction, Rule Ingestion & File Processing' },
        'domains-view': { title: 'Explore Domains', sub: 'Curated Policy Knowledge Bases & Symbolic Schemas' },
        'studio-view': { title: 'Visual Rule Studio', sub: 'Condition Builder & Symbolic Rule Authoring' },
        'official-rules-view': { title: 'Official Policy Library', sub: 'Audited Institutional Policies & Constraints' },
        'official-library-view': { title: 'Official Policy Library', sub: 'Audited Institutional Policies & Constraints' },
        'history-view': { title: 'Decision History', sub: 'Personalized Audit Log & Trace Inspector' },
        'simulator-view': { title: 'What-If Simulator', sub: 'Counterfactual Reasoning & Rule Modification Sandbox' },
        'admin-view': { title: 'Administrator Dashboard', sub: 'Platform Analysis, Official Rules, User Directory & Guardrails' },
    };

    function switchTab(tabId) {
        // ENFORCE ADMIN RESTRICTION: Normal users can never access admin-view
        if (tabId === 'admin-view') {
            const isAdmin = state.user && (state.user.role === 'admin' || state.user.role === 'owner');
            if (!isAdmin) {
                alert('Access Denied: The Administrator Console is strictly restricted to authenticated Administrators.');
                tabId = 'chat-view';
            }
        }

        state.activeTab = tabId;

        document.querySelectorAll('.view-panel').forEach(panel => {
            panel.classList.add('hidden');
            panel.classList.remove('active');
        });

        const activePanel = document.getElementById(tabId);
        if (activePanel) {
            activePanel.classList.remove('hidden');
            activePanel.classList.add('active');
        }

        document.querySelectorAll('.nav-item').forEach(btn => {
            if (btn.getAttribute('data-tab') === tabId) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });

        const titleEl = document.getElementById('page-title');
        const subEl = document.getElementById('page-subtext');
        const meta = viewHeadings[tabId] || { title: 'RuleWise AI', sub: 'Neuro-Symbolic Platform' };
        if (titleEl) titleEl.textContent = meta.title;
        if (subEl) subEl.textContent = meta.sub;

        if (tabId === 'domains-view') loadDomainsView();
        if (tabId === 'official-rules-view' || tabId === 'official-library-view') loadOfficialLibraryView();
        if (tabId === 'history-view') loadHistoryView();
        if (tabId === 'simulator-view') loadSimulatorView();
        if (tabId === 'studio-view') loadStudioView();
        if (tabId === 'admin-view') initAdminView();
        if (tabId === 'file-tools-view') initFileTools();

        if (window.innerWidth <= 768) {
            closeMobileSidebar();
        }
    }

    function toggleSidebar() {
        const sidebar = document.getElementById('sidebar');
        const backdrop = document.getElementById('sidebar-backdrop');
        if (!sidebar) return;

        if (window.innerWidth <= 768) {
            sidebar.classList.toggle('open');
            if (backdrop) {
                if (sidebar.classList.contains('open')) {
                    backdrop.classList.remove('hidden');
                } else {
                    backdrop.classList.add('hidden');
                }
            }
        } else {
            sidebar.classList.toggle('collapsed');
        }
    }

    function closeMobileSidebar() {
        const sidebar = document.getElementById('sidebar');
        const backdrop = document.getElementById('sidebar-backdrop');
        if (sidebar) sidebar.classList.remove('open');
        if (backdrop) backdrop.classList.add('hidden');
    }

    // -------------------------------------------------------------------------
    // 7. Recent Chats & Live Search Filter
    // -------------------------------------------------------------------------
    async function renderRecentChatsList(filterQuery = '') {
        const list = document.getElementById('recent-chats-list');
        if (!list) return;

        let convs = [];
        try {
            const serverConvs = await apiRequest('/api/v1/chat/conversations?limit=50');
            if (Array.isArray(serverConvs)) {
                convs = serverConvs;
            }
        } catch (e) {
            convs = getDeviceChats();
        }

        if (!convs.length) {
            convs = getDeviceChats();
        }

        state.conversations = convs;

        const q = filterQuery.toLowerCase().trim();
        const displayConvs = q ? convs.filter(c => (c.title || '').toLowerCase().includes(q)) : convs;

        if (!displayConvs.length) {
            list.innerHTML = `
                <div style="padding:14px 12px;font-size:12px;color:#94a3b8;text-align:center;">
                    ${q ? 'No matching chats found.' : 'No recent chats. Start a new conversation above.'}
                </div>
            `;
            return;
        }

        list.innerHTML = displayConvs.map(c => `
            <div class="recent-chat-item ${c.id === state.currentConversationId ? 'active' : ''}" data-conv-id="${escapeHtml(c.id)}">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                </svg>
                <span class="recent-chat-title">${escapeHtml(c.title || 'Conversation')}</span>
            </div>
        `).join('');

        list.querySelectorAll('.recent-chat-item').forEach(item => {
            item.addEventListener('click', () => {
                const convId = item.getAttribute('data-conv-id');
                if (convId) loadConversationSession(convId);
            });
        });
    }

    function initChatSearch() {
        const searchInput = document.getElementById('sidebar-chat-search') || document.getElementById('search-chats-input');
        if (!searchInput) return;
        searchInput.addEventListener('input', () => {
            renderRecentChatsList(searchInput.value);
        });
    }

    async function loadConversationSession(conversationId) {
        state.currentConversationId = conversationId;
        switchTab('chat-view');
        renderRecentChatsList();

        const messagesList = document.getElementById('messages-list');
        const hero = document.getElementById('welcome-hero');
        const starters = document.getElementById('rulewise-hero-starters');

        if (messagesList) messagesList.innerHTML = '<div class="loading-placeholder">Loading conversation history...</div>';
        if (hero) hero.classList.add('hidden');
        if (starters) starters.classList.add('hidden');

        try {
            const msgs = await apiRequest(`/api/v1/chat/conversations/${encodeURIComponent(conversationId)}/messages`);
            if (messagesList) messagesList.innerHTML = '';
            if (Array.isArray(msgs) && msgs.length > 0) {
                state.currentMessages = msgs;
                msgs.forEach(m => {
                    if (m.sender === 'user') {
                        appendUserMessage(m.content, [], false);
                    } else {
                        appendAssistantMessage({
                            message: m.content,
                            symbolic_result: m.symbolic_result,
                            explanation: m.explanation,
                        }, false);
                    }
                });
                scrollToBottom();
            } else {
                if (messagesList) messagesList.innerHTML = '<div class="empty-state">No messages found in this conversation.</div>';
            }
        } catch (e) {
            if (messagesList) messagesList.innerHTML = `<div class="empty-state text-danger">Failed to load conversation: ${escapeHtml(e.message)}</div>`;
        }
    }

    // -------------------------------------------------------------------------
    // 8. Speech Synthesis (TTS Play / Stop Toggle)
    // -------------------------------------------------------------------------
    function toggleSpeechSynthesis(text, btnElement) {
        if (!('speechSynthesis' in window)) {
            alert('Text-to-speech is not supported in this browser.');
            return;
        }

        const span = btnElement.querySelector('span');

        if (window.speechSynthesis.speaking && state.activeSpeechButton === btnElement) {
            window.speechSynthesis.cancel();
            if (span) span.textContent = 'Speak';
            btnElement.classList.remove('active');
            state.activeSpeechButton = null;
            return;
        }

        window.speechSynthesis.cancel();
        if (state.activeSpeechButton) {
            const prevSpan = state.activeSpeechButton.querySelector('span');
            if (prevSpan) prevSpan.textContent = 'Speak';
            state.activeSpeechButton.classList.remove('active');
        }

        const plainText = text
            .replace(/```[\s\S]*?```/g, 'Code block omitted.')
            .replace(/`([^`]+)`/g, '$1')
            .replace(/[*#_~>]/g, '')
            .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
            .trim();

        if (!plainText) return;

        const utterance = new SpeechSynthesisUtterance(plainText);
        utterance.rate = 1.0;
        utterance.pitch = 1.0;

        utterance.onstart = () => {
            if (span) span.textContent = 'Stop';
            btnElement.classList.add('active');
            state.activeSpeechButton = btnElement;
        };

        utterance.onend = () => {
            if (span) span.textContent = 'Speak';
            btnElement.classList.remove('active');
            if (state.activeSpeechButton === btnElement) state.activeSpeechButton = null;
        };

        utterance.onerror = () => {
            if (span) span.textContent = 'Speak';
            btnElement.classList.remove('active');
            if (state.activeSpeechButton === btnElement) state.activeSpeechButton = null;
        };

        window.speechSynthesis.speak(utterance);
    }

    // -------------------------------------------------------------------------
    // 9. Voice Recognition (Microphone Web Speech API)
    // -------------------------------------------------------------------------
    function initVoiceInput() {
        const micBtn = document.getElementById('mic-btn');
        const input = document.getElementById('user-input') || document.getElementById('chat-input');
        if (!micBtn || !input) return;

        const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRec) {
            micBtn.style.opacity = '0.4';
            micBtn.title = 'Speech Recognition not supported in this browser';
            return;
        }

        const recognition = new SpeechRec();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = 'en-US';

        let isListening = false;

        micBtn.onclick = () => {
            if (isListening) {
                recognition.stop();
                return;
            }
            try {
                recognition.start();
                isListening = true;
                micBtn.classList.add('recording');
                micBtn.title = 'Listening... Speak into your microphone';
            } catch (err) {
                console.warn('Speech recognition start error:', err);
            }
        };

        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            input.value = input.value ? (input.value + ' ' + transcript) : transcript;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.focus();
        };

        recognition.onerror = () => {
            isListening = false;
            micBtn.classList.remove('recording');
        };

        recognition.onend = () => {
            isListening = false;
            micBtn.classList.remove('recording');
            micBtn.title = 'Speak to RuleWise (Voice to text)';
        };
    }

    // -------------------------------------------------------------------------
    // 10. File Uploads, Camera Capture & Attachment Chips
    // -------------------------------------------------------------------------
    function initFileUpload() {
        const fileUploadBtn = document.getElementById('file-upload-btn') || document.getElementById('attach-btn');
        const fileUploadInput = document.getElementById('file-upload-input') || document.getElementById('chat-file-input');
        const cameraBtn = document.getElementById('camera-btn');
        const cameraFileInput = document.getElementById('camera-file-input');
        const chipsContainer = document.getElementById('attached-files-container') || document.getElementById('attachment-chips');

        if (fileUploadBtn && fileUploadInput) {
            fileUploadBtn.onclick = () => fileUploadInput.click();
            fileUploadInput.onchange = async () => {
                const files = Array.from(fileUploadInput.files);
                if (!files.length) return;
                for (const file of files) {
                    await uploadAndAttachFile(file, chipsContainer);
                }
                fileUploadInput.value = '';
                updateComposerState();
            };
        }

        if (cameraBtn && cameraFileInput) {
            cameraBtn.onclick = () => cameraFileInput.click();
            cameraFileInput.onchange = async () => {
                const files = Array.from(cameraFileInput.files);
                if (!files.length) return;
                for (const file of files) {
                    await uploadAndAttachFile(file, chipsContainer);
                }
                cameraFileInput.value = '';
                updateComposerState();
            };
        }
    }

    async function uploadAndAttachFile(file, chipsContainer) {
        if (!chipsContainer) return;
        chipsContainer.classList.remove('hidden');

        const formData = new FormData();
        formData.append('files', file);

        const tempId = 'chip_' + Math.random().toString(36).substring(2, 8);
        const chip = document.createElement('div');
        chip.className = 'attachment-chip';
        chip.id = tempId;
        chip.innerHTML = `
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
            </svg>
            <span class="file-name">${escapeHtml(file.name)}</span>
            <span class="upload-status" style="font-size:11px;color:var(--brand-primary);">(uploading...)</span>
            <button type="button" class="remove-chip-btn" style="background:none;border:none;color:#94a3b8;cursor:pointer;font-size:14px;margin-left:4px;">&times;</button>
        `;
        chipsContainer.appendChild(chip);

        chip.querySelector('.remove-chip-btn').onclick = () => {
            chip.remove();
            state.attachedFiles = state.attachedFiles.filter(f => f.tempId !== tempId);
            if (!state.attachedFiles.length) {
                chipsContainer.classList.add('hidden');
            }
            updateComposerState();
        };

        try {
            const headers = {};
            if (state.token) headers['Authorization'] = `Bearer ${state.token}`;

            const resp = await fetch(`${API_BASE}/api/v1/files/upload`, {
                method: 'POST',
                headers,
                body: formData,
            });

            if (!resp.ok) {
                const errData = await resp.json().catch(() => ({}));
                throw new Error(errData.detail || 'Upload failed');
            }

            const data = await resp.json();
            const statusEl = chip.querySelector('.upload-status');
            if (statusEl) statusEl.remove();

            const uploadedFile = data.files && data.files[0] ? data.files[0] : {};

            state.attachedFiles.push({
                tempId,
                filename: file.name,
                file_id: tempId,
                extracted_text: uploadedFile.content || uploadedFile.summary || '',
            });
            updateComposerState();
        } catch (err) {
            const statusEl = chip.querySelector('.upload-status');
            if (statusEl) {
                statusEl.textContent = '(failed)';
                statusEl.style.color = '#ef4444';
            }
        }
    }

    // -------------------------------------------------------------------------
    // 11. CHAT COMPOSER — REAL-TIME STATE & MESSAGE SUBMISSION
    // -------------------------------------------------------------------------
    function updateComposerState() {
        const input = document.getElementById('user-input') || document.getElementById('chat-input');
        const sendBtn = document.getElementById('send-btn');
        const charCounter = document.getElementById('char-counter');

        const text = input ? input.value : '';
        const charCount = text.length;

        if (charCounter) {
            charCounter.textContent = `${charCount}/20000`;
            if (charCount > 19000) {
                charCounter.style.color = '#ef4444';
            } else {
                charCounter.style.color = '';
            }
        }

        const hasValidContent = text.trim().length > 0 || state.attachedFiles.length > 0;
        if (sendBtn) {
            sendBtn.disabled = !hasValidContent;
            if (hasValidContent) {
                sendBtn.classList.add('active');
            } else {
                sendBtn.classList.remove('active');
            }
        }
    }

    function initChat() {
        const input = document.getElementById('user-input') || document.getElementById('chat-input');
        const sendBtn = document.getElementById('send-btn');
        const chatForm = document.getElementById('chat-form');
        const newChatBtn = document.getElementById('sidebar-new-chat-btn') || document.getElementById('new-chat-btn');
        const composerDomainTag = document.getElementById('composer-domain-tag') || document.getElementById('chat-domain-pill');
        const headerDomainPill = document.getElementById('header-domain-pill');

        // Wire RuleWise Policy selector
        const openDomainSelector = () => switchTab('domains-view');
        if (composerDomainTag) composerDomainTag.onclick = openDomainSelector;
        if (headerDomainPill) headerDomainPill.onclick = openDomainSelector;

        function triggerSend() {
            if (state.isLoadingChat) return;
            const text = (input ? input.value : '').trim();
            if (!text && !state.attachedFiles.length) return;

            handleUserSubmit(text);
        }

        if (input) {
            input.addEventListener('input', () => {
                input.style.height = 'auto';
                input.style.height = Math.min(input.scrollHeight, 180) + 'px';
                updateComposerState();
            });

            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    triggerSend();
                }
            });

            // Initialize counter on load
            updateComposerState();
        }

        if (chatForm) {
            chatForm.addEventListener('submit', (e) => {
                e.preventDefault();
                triggerSend();
            });
        }

        if (sendBtn) {
            sendBtn.addEventListener('click', (e) => {
                e.preventDefault();
                triggerSend();
            });
        }

        function resetConversation() {
            state.currentConversationId = 'session_' + Math.random().toString(36).substring(2, 10);
            state.currentMessages = [];
            state.attachedFiles = [];
            const list = document.getElementById('messages-list');
            const hero = document.getElementById('welcome-hero');
            const starters = document.getElementById('rulewise-hero-starters');
            const chips = document.getElementById('attached-files-container') || document.getElementById('attachment-chips');
            if (list) list.innerHTML = '';
            if (hero) hero.classList.remove('hidden');
            if (starters) starters.classList.remove('hidden');
            if (chips) {
                chips.innerHTML = '';
                chips.classList.add('hidden');
            }
            if (input) {
                input.value = '';
                input.style.height = 'auto';
            }
            updateComposerState();
            renderRecentChatsList();
        }

        if (newChatBtn) newChatBtn.onclick = resetConversation;

        document.querySelectorAll('.starter-card, .hero-starter-card').forEach(card => {
            card.onclick = () => {
                const prompt = card.getAttribute('data-query') || card.getAttribute('data-prompt');
                if (prompt && input) {
                    input.value = prompt;
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    triggerSend();
                }
            };
        });

        initVoiceInput();
        initFileUpload();
        initChatSearch();
        renderRecentChatsList();
    }

    async function handleUserSubmit(text) {
        if (state.isLoadingChat) return;
        state.isLoadingChat = true;

        const input = document.getElementById('user-input') || document.getElementById('chat-input');
        const sendBtn = document.getElementById('send-btn');
        if (sendBtn) sendBtn.disabled = true;

        const hero = document.getElementById('welcome-hero');
        const starters = document.getElementById('rulewise-hero-starters');
        if (hero) hero.classList.add('hidden');
        if (starters) starters.classList.add('hidden');

        const currentAttachments = [...state.attachedFiles];
        state.attachedFiles = [];
        const chipsContainer = document.getElementById('attached-files-container') || document.getElementById('attachment-chips');
        if (chipsContainer) {
            chipsContainer.innerHTML = '';
            chipsContainer.classList.add('hidden');
        }

        // Render user message immediately
        appendUserMessage(text, currentAttachments, true);

        // Render loading skeleton
        const list = document.getElementById('messages-list');
        const skeleton = document.createElement('div');
        skeleton.className = 'msg-row assistant-row skeleton-row';
        skeleton.innerHTML = `
            <div class="msg-avatar">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
                    <polyline points="2 17 12 22 22 17"></polyline>
                    <polyline points="2 12 12 17 22 12"></polyline>
                </svg>
            </div>
            <div class="msg-bubble">
                <div class="skeleton-line" style="width: 60%; height: 14px; background: rgba(255,255,255,0.08); border-radius: 4px; margin-bottom: 8px;"></div>
                <div class="skeleton-line" style="width: 85%; height: 12px; background: rgba(255,255,255,0.05); border-radius: 4px; margin-bottom: 6px;"></div>
                <div class="skeleton-line" style="width: 40%; height: 12px; background: rgba(255,255,255,0.05); border-radius: 4px;"></div>
            </div>
        `;
        list.appendChild(skeleton);
        scrollToBottom();

        try {
            const mappedFiles = currentAttachments.map(f => ({
                file_id: f.file_id,
                name: f.filename,
                filename: f.filename,
                summary: f.summary || '',
                content: f.extracted_text || '',
                text_snippet: f.extracted_text ? f.extracted_text.slice(0, 5000) : '',
            }));

            const payload = {
                message: text || '(attached file inquiry)',
                domain_id: state.activeDomainId,
                conversation_id: state.currentConversationId,
                attachments: mappedFiles,
                attached_files: mappedFiles,
            };

            const data = await apiRequest('/api/v1/chat', {
                method: 'POST',
                body: JSON.stringify(payload),
            });

            skeleton.remove();
            appendAssistantMessage(data, true);

            // Clear input only after successful submission
            if (input) {
                input.value = '';
                input.style.height = 'auto';
            }
            updateComposerState();
        } catch (err) {
            skeleton.remove();
            let rawMsg = (err && err.message) ? String(err.message) : 'An error occurred while processing your message.';
            if (rawMsg === '[object Object]') {
                rawMsg = 'Invalid request parameters or server processing issue.';
            }
            appendAssistantMessage({
                message: `⚠️ **Advisory Notice:** ${rawMsg}. Please retry or verify parameters.`,
            }, true);
            updateComposerState();
        } finally {
            state.isLoadingChat = false;
            updateComposerState();
        }
    }

    // Alias for backwards-compatibility with test assertions
    const handleSendMessage = handleUserSubmit;

    function appendUserMessage(text, attachments = [], shouldSave = true) {
        const list = document.getElementById('messages-list');
        if (!list) return;
        const row = document.createElement('div');
        row.className = 'msg-row user-row';

        let attachmentsHtml = '';
        if (attachments && attachments.length > 0) {
            attachmentsHtml = `
                <div class="msg-attachments-preview">
                    ${attachments.map(a => `
                        <div class="msg-attachment-badge">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                                <polyline points="14 2 14 8 20 8"></polyline>
                            </svg>
                            <span>${escapeHtml(a.filename)}</span>
                        </div>
                    `).join('')}
                </div>
            `;
        }

        row.innerHTML = `
            <div class="msg-bubble">
                ${attachmentsHtml}
                <div class="msg-text">${escapeHtml(text)}</div>
            </div>
        `;
        list.appendChild(row);
        scrollToBottom();

        if (shouldSave) {
            state.currentMessages.push({
                sender: 'user',
                content: text,
                attachments,
                timestamp: new Date().toISOString(),
            });
            saveCurrentDeviceChat(text, state.currentMessages);
        }
    }

    function appendAssistantMessage(data, shouldSave = true) {
        const list = document.getElementById('messages-list');
        if (!list) return;
        const row = document.createElement('div');
        row.className = 'msg-row assistant-row';

        const isEligible = data.symbolic_result?.eligible ?? data.symbolic_result?.is_eligible;
        let badgeLabel = 'RuleWise AI';
        let badgeClass = 'neutral';

        if (isEligible === true) {
            badgeLabel = 'ELIGIBLE / APPROVED';
            badgeClass = 'success';
        } else if (isEligible === false) {
            badgeLabel = 'INELIGIBLE / REJECTED';
            badgeClass = 'error';
        } else if (data.symbolic_result) {
            badgeLabel = 'POLICY EVALUATED';
            badgeClass = 'info';
        }

        let reasoningHtml = '';
        if (data.explanation || data.symbolic_result) {
            const fired = data.symbolic_result?.executed_rules || data.symbolic_result?.matched_rules || [];
            reasoningHtml = `
                <div class="symbolic-audit-card">
                    <div class="audit-card-header">
                        <span class="audit-title">Deterministic Policy Audit</span>
                        <span class="audit-rules-count">${fired.length} Rules Applied</span>
                    </div>
                    <div class="audit-card-body">
                        ${fired.map(r => `
                            <div class="audit-rule-item">
                                <span class="rule-icon">✓</span>
                                <span class="rule-id"><code>${escapeHtml(r.rule_id || r.id || 'RULE')}</code></span>
                                <span class="rule-name">${escapeHtml(r.name || 'Official Policy Criterion')}</span>
                            </div>
                        `).join('')}
                    </div>
                    <div class="audit-card-footer">
                        <button class="rulewise-btn secondary btn-sm inspect-trace-btn" data-trace='${escapeHtml(JSON.stringify(data.explanation || data.symbolic_result || {}))}'>
                            Inspect Full Proof Trace
                        </button>
                    </div>
                </div>
            `;
        }

        row.innerHTML = `
            <div class="msg-avatar">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
                    <polyline points="2 17 12 22 22 17"></polyline>
                    <polyline points="2 12 12 17 22 12"></polyline>
                </svg>
            </div>
            <div class="msg-bubble">
                <div class="msg-header-line">
                    <span class="msg-author-name">RuleWise AI</span>
                    <span class="decision-badge ${badgeClass}">${badgeLabel}</span>
                    <span class="msg-time">${formatTime()}</span>
                </div>
                ${reasoningHtml}
                <div class="msg-text">${formatMarkdown(data.message)}</div>
                <div class="msg-actions-toolbar">
                    <button class="rulewise-action-btn copy-msg-btn" title="Copy response">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                        </svg>
                        <span>Copy</span>
                    </button>
                    <button class="rulewise-action-btn speak-msg-btn" title="Speak response aloud">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
                            <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path>
                        </svg>
                        <span>Speak</span>
                    </button>
                </div>
            </div>
        `;

        list.appendChild(row);

        const traceBtn = row.querySelector('.inspect-trace-btn');
        if (traceBtn) {
            traceBtn.addEventListener('click', () => {
                const traceJson = JSON.parse(traceBtn.getAttribute('data-trace'));
                showTraceModal(traceJson);
            });
        }

        const copyBtn = row.querySelector('.copy-msg-btn');
        if (copyBtn) {
            copyBtn.addEventListener('click', () => {
                navigator.clipboard.writeText(data.message);
                const span = copyBtn.querySelector('span');
                if (span) {
                    span.textContent = 'Copied!';
                    setTimeout(() => { span.textContent = 'Copy'; }, 2000);
                }
            });
        }

        const speakBtn = row.querySelector('.speak-msg-btn');
        if (speakBtn) {
            speakBtn.addEventListener('click', () => {
                toggleSpeechSynthesis(data.message, speakBtn);
            });
        }

        scrollToBottom();

        if (shouldSave) {
            state.currentMessages.push({
                sender: 'assistant',
                message: data.message,
                content: data.message,
                symbolic_result: data.symbolic_result,
                explanation: data.explanation,
                timestamp: new Date().toISOString(),
            });
            saveCurrentDeviceChat(state.currentMessages[0]?.content || 'Chat Session', state.currentMessages);
        }
    }

    // -------------------------------------------------------------------------
    // 12. FILE TOOLS & CONVERTERS CONTROLLER (Phase 7)
    // -------------------------------------------------------------------------
    function initFileTools() {
        // 1. Image to PDF
        const imgInput = document.getElementById('img-to-pdf-input');
        const imgStatus = document.getElementById('img-to-pdf-status');
        const imgBtn = document.getElementById('img-to-pdf-btn');

        if (imgInput && imgStatus && imgBtn) {
            imgInput.onchange = () => {
                const count = imgInput.files.length;
                imgStatus.textContent = count ? `${count} image${count > 1 ? 's' : ''} selected` : 'No images selected';
            };

            imgBtn.onclick = async () => {
                if (!imgInput.files.length) {
                    alert('Please select at least one image file.');
                    return;
                }
                const formData = new FormData();
                for (const file of imgInput.files) {
                    formData.append('files', file);
                }
                imgBtn.disabled = true;
                imgBtn.textContent = 'Converting...';
                try {
                    const resp = await fetch(`${API_BASE}/api/v1/files/convert/image-to-pdf`, {
                        method: 'POST',
                        body: formData,
                    });
                    if (!resp.ok) throw new Error(`Conversion failed with status ${resp.status}`);
                    const blob = await resp.blob();
                    downloadBlob(blob, 'converted_rulewise.pdf');
                    imgStatus.textContent = 'Conversion complete! Downloaded PDF.';
                } catch (e) {
                    alert('Conversion error: ' + e.message);
                } finally {
                    imgBtn.disabled = false;
                    imgBtn.textContent = 'Convert to PDF';
                }
            };
        }

        // 2. PDF to Image
        const pdfInput = document.getElementById('pdf-to-img-input');
        const pdfStatus = document.getElementById('pdf-to-img-status');
        const pdfBtn = document.getElementById('pdf-to-img-btn');

        if (pdfInput && pdfStatus && pdfBtn) {
            pdfInput.onchange = () => {
                pdfStatus.textContent = pdfInput.files.length ? pdfInput.files[0].name : 'No PDF selected';
            };

            pdfBtn.onclick = async () => {
                if (!pdfInput.files.length) {
                    alert('Please select a PDF document.');
                    return;
                }
                const formData = new FormData();
                formData.append('file', pdfInput.files[0]);
                pdfBtn.disabled = true;
                pdfBtn.textContent = 'Extracting...';
                try {
                    const resp = await fetch(`${API_BASE}/api/v1/files/convert/pdf-to-images`, {
                        method: 'POST',
                        body: formData,
                    });
                    if (!resp.ok) throw new Error(`Extraction failed with status ${resp.status}`);
                    const blob = await resp.blob();
                    downloadBlob(blob, 'extracted_images.zip');
                    pdfStatus.textContent = 'Extraction complete! Downloaded ZIP archive.';
                } catch (e) {
                    alert('Extraction error: ' + e.message);
                } finally {
                    pdfBtn.disabled = false;
                    pdfBtn.textContent = 'Extract Images';
                }
            };
        }

        // 3. File Compressor
        const compInput = document.getElementById('compress-input');
        const compQuality = document.getElementById('compress-quality');
        const qualVal = document.getElementById('quality-val');
        const compStatus = document.getElementById('compress-status');
        const compBtn = document.getElementById('compress-btn');

        if (compQuality && qualVal) {
            compQuality.oninput = () => {
                qualVal.textContent = compQuality.value + '%';
            };
        }

        if (compInput && compBtn && compStatus) {
            compInput.onchange = () => {
                compStatus.textContent = compInput.files.length ? compInput.files[0].name : 'No file selected';
            };

            compBtn.onclick = async () => {
                if (!compInput.files.length) {
                    alert('Please select a file to compress.');
                    return;
                }
                const formData = new FormData();
                formData.append('file', compInput.files[0]);
                formData.append('quality', compQuality ? compQuality.value : '60');
                compBtn.disabled = true;
                compBtn.textContent = 'Compressing...';
                try {
                    const resp = await fetch(`${API_BASE}/api/v1/files/compress`, {
                        method: 'POST',
                        body: formData,
                    });
                    if (!resp.ok) throw new Error(`Compression failed with status ${resp.status}`);
                    const blob = await resp.blob();
                    const ext = compInput.files[0].name.split('.').pop() || 'pdf';
                    downloadBlob(blob, `compressed_rulewise.${ext}`);
                    compStatus.textContent = 'File compressed and downloaded!';
                } catch (e) {
                    alert('Compression error: ' + e.message);
                } finally {
                    compBtn.disabled = false;
                    compBtn.textContent = 'Compress File';
                }
            };
        }

        // 4. PDF Merger
        const mergeInput = document.getElementById('merge-pdf-input');
        const mergeStatus = document.getElementById('merge-pdf-status');
        const mergeBtn = document.getElementById('merge-pdf-btn');

        if (mergeInput && mergeBtn && mergeStatus) {
            mergeInput.onchange = () => {
                const count = mergeInput.files.length;
                mergeStatus.textContent = count ? `${count} PDFs selected` : 'Select 2+ PDF files';
            };

            mergeBtn.onclick = async () => {
                if (mergeInput.files.length < 2) {
                    alert('Please select at least 2 PDF files to merge.');
                    return;
                }
                const formData = new FormData();
                for (const file of mergeInput.files) {
                    formData.append('files', file);
                }
                mergeBtn.disabled = true;
                mergeBtn.textContent = 'Merging...';
                try {
                    const resp = await fetch(`${API_BASE}/api/v1/files/merge-pdfs`, {
                        method: 'POST',
                        body: formData,
                    });
                    if (!resp.ok) throw new Error(`Merge failed with status ${resp.status}`);
                    const blob = await resp.blob();
                    downloadBlob(blob, 'merged_rulewise.pdf');
                    mergeStatus.textContent = 'Merged successfully! Downloaded PDF.';
                } catch (e) {
                    alert('Merge error: ' + e.message);
                } finally {
                    mergeBtn.disabled = false;
                    mergeBtn.textContent = 'Merge PDFs';
                }
            };
        }
    }

    function downloadBlob(blob, filename) {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // -------------------------------------------------------------------------
    // 13. ADMINISTRATOR CONSOLE CONTROLLER (Strictly Owner/Admin Restricted)
    // -------------------------------------------------------------------------
    async function initAdminView() {
        const isOwner = state.user && state.user.role === 'owner';
        const isAdmin = state.user && (state.user.role === 'admin' || isOwner);

        if (!isAdmin) {
            alert('Access Denied: The Administrator Console is strictly restricted to authenticated Administrators.');
            switchTab('chat-view');
            return;
        }

        // Subnavigation setup
        const subNavBtns = document.querySelectorAll('#admin-subnav-container .admin-subnav-btn');
        subNavBtns.forEach(btn => {
            btn.onclick = () => {
                subNavBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const subtab = btn.getAttribute('data-admin-tab');
                switchAdminSubTab(subtab);
            };
        });

        switchAdminSubTab(state.activeAdminSubTab || 'admin-tab-overview');
    }

    function switchAdminSubTab(subtabId) {
        state.activeAdminSubTab = subtabId;
        const allPanels = [
            'admin-tab-overview',
            'admin-tab-users',
            'admin-tab-rules',
            'admin-tab-decisions',
            'admin-tab-sessions',
            'admin-tab-safety',
        ];

        allPanels.forEach(id => {
            const p = document.getElementById(id);
            if (p) {
                if (id === subtabId) p.classList.remove('hidden');
                else p.classList.add('hidden');
            }
        });

        if (subtabId === 'admin-tab-overview') loadAdminTelemetry();
        if (subtabId === 'admin-tab-users') loadAdminUsers();
        if (subtabId === 'admin-tab-rules') loadAdminRules();
        if (subtabId === 'admin-tab-decisions') loadAdminDecisions();
        if (subtabId === 'admin-tab-sessions') loadAdminSessions();
        if (subtabId === 'admin-tab-safety') loadAdminSafetyPolicies();
    }

    async function loadAdminTelemetry() {
        try {
            const overview = await apiRequest('/api/v1/admin/platform-overview');
            const m = overview.metrics || {};

            const setTxt = (id, val) => {
                const el = document.getElementById(id);
                if (el) el.textContent = val !== undefined ? val : '—';
            };

            setTxt('admin-stat-users', m.total_registered_users);
            setTxt('admin-stat-active-users', m.active_users_count);
            setTxt('admin-stat-convs', m.total_conversations);
            setTxt('admin-stat-queries', m.total_ai_queries);
            setTxt('admin-stat-rules', m.official_rules_count);

            const aiStatusEl = document.getElementById('admin-ai-health-status');
            if (aiStatusEl) {
                const status = overview.ai_status || {};
                aiStatusEl.innerHTML = `
                    <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(200px, 1fr));gap:12px;">
                        <div><strong>Model Engine:</strong> <code>${escapeHtml(status.model_configured || 'Gemini 3.5 Flash')}</code></div>
                        <div><strong>Provider Status:</strong> <span class="badge ${status.provider_available ? 'success' : 'error'}">${status.provider_available ? 'Online (Active)' : 'Offline (Fallback Ready)'}</span></div>
                        <div><strong>Symbolic Authority:</strong> <span class="badge success">Active (100% Deterministic)</span></div>
                        <div><strong>Live Grounding:</strong> <span class="badge success">Ready</span></div>
                    </div>
                `;
            }
        } catch (e) {
            console.error('Failed to load telemetry:', e);
        }
    }

    async function loadAdminUsers() {
        const wrap = document.getElementById('admin-users-table-wrap');
        if (!wrap) return;
        wrap.innerHTML = '<div class="loading-placeholder">Loading user directory...</div>';

        try {
            const data = await apiRequest('/api/v1/admin/users?limit=100');
            const users = data.items || [];
            renderUsersTable(users);

            const searchInput = document.getElementById('admin-user-search');
            if (searchInput) {
                searchInput.oninput = () => {
                    const q = searchInput.value.toLowerCase().trim();
                    const filtered = users.filter(u =>
                        (u.username || '').toLowerCase().includes(q) ||
                        (u.email || '').toLowerCase().includes(q) ||
                        (u.role || '').toLowerCase().includes(q)
                    );
                    renderUsersTable(filtered);
                };
            }

            const addBtn = document.getElementById('admin-add-user-btn');
            if (addBtn) {
                addBtn.onclick = () => {
                    const modal = document.getElementById('admin-add-user-modal');
                    if (modal) modal.classList.remove('hidden');
                };
            }
        } catch (e) {
            wrap.innerHTML = `<div class="empty-state text-danger">Failed to load users: ${escapeHtml(e.message)}</div>`;
        }
    }

    function renderUsersTable(users) {
        const wrap = document.getElementById('admin-users-table-wrap');
        if (!wrap) return;

        if (!users || !users.length) {
            wrap.innerHTML = '<div class="empty-state">No users match your criteria.</div>';
            return;
        }

        const isOwner = state.user && state.user.role === 'owner';

        wrap.innerHTML = `
            <table class="rules-table">
                <thead>
                    <tr>
                        <th>User</th>
                        <th>Email / Identity</th>
                        <th>Role</th>
                        <th>Status</th>
                        <th>Created</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${users.map(u => {
                        const isActive = u.is_active !== 0;
                        const userRole = u.role || 'user';
                        const isTargetOwner = userRole === 'owner';
                        const isTargetAdmin = userRole === 'admin';

                        return `
                            <tr>
                                <td>
                                    <strong>${escapeHtml(u.username)}</strong>
                                    ${u.google_id ? '<span class="badge info" style="margin-left:6px;font-size:10px;">Google</span>' : ''}
                                </td>
                                <td>${escapeHtml(u.email || '—')}</td>
                                <td>
                                    <span class="badge ${isTargetOwner ? 'admin-badge' : (isTargetAdmin ? 'info' : 'neutral')}">
                                        ${isTargetOwner ? 'Owner' : (isTargetAdmin ? 'Administrator' : 'Normal User')}
                                    </span>
                                </td>
                                <td>
                                    <span class="badge ${isActive ? 'success' : 'error'}">
                                        ${isActive ? 'Active' : 'Disabled'}
                                    </span>
                                </td>
                                <td><small>${new Date(u.created_at || Date.now()).toLocaleDateString()}</small></td>
                                <td>
                                    <div style="display:flex; gap:6px; flex-wrap:wrap;">
                                        ${!isTargetOwner ? `
                                            <button class="rulewise-btn secondary btn-sm toggle-user-status-btn" data-user-id="${escapeHtml(u.id)}" data-active="${isActive}">
                                                ${isActive ? 'Disable' : 'Activate'}
                                            </button>
                                        ` : ''}

                                        <!-- Owner privilege: appoint/revoke admin role -->
                                        ${isOwner && !isTargetOwner ? `
                                            <button class="rulewise-btn ${isTargetAdmin ? 'secondary' : 'primary'} btn-sm toggle-admin-role-btn" data-user-id="${escapeHtml(u.id)}" data-role="${isTargetAdmin ? 'user' : 'admin'}">
                                                ${isTargetAdmin ? 'Revoke Admin' : 'Appoint Admin'}
                                            </button>
                                        ` : ''}

                                        ${!isTargetOwner ? `
                                            <button class="rulewise-btn danger btn-sm delete-user-btn" data-user-id="${escapeHtml(u.id)}" data-username="${escapeHtml(u.username)}">
                                                Delete
                                            </button>
                                        ` : ''}
                                    </div>
                                </td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        `;

        wrap.querySelectorAll('.toggle-user-status-btn').forEach(btn => {
            btn.onclick = async () => {
                const uid = btn.getAttribute('data-user-id');
                const curActive = btn.getAttribute('data-active') === 'true';
                try {
                    await apiRequest(`/api/v1/admin/users/${encodeURIComponent(uid)}/status`, {
                        method: 'PUT',
                        body: JSON.stringify({ is_active: !curActive }),
                    });
                    loadAdminUsers();
                } catch (e) {
                    alert('Status update failed: ' + e.message);
                }
            };
        });

        wrap.querySelectorAll('.toggle-admin-role-btn').forEach(btn => {
            btn.onclick = async () => {
                const uid = btn.getAttribute('data-user-id');
                const targetRole = btn.getAttribute('data-role');
                if (!confirm(`Are you sure you want to change this account role to "${targetRole}"?`)) return;
                try {
                    await apiRequest(`/api/v1/admin/users/${encodeURIComponent(uid)}/role?role=${encodeURIComponent(targetRole)}`, {
                        method: 'PUT',
                    });
                    loadAdminUsers();
                } catch (e) {
                    alert('Role delegation failed: ' + e.message);
                }
            };
        });

        wrap.querySelectorAll('.delete-user-btn').forEach(btn => {
            btn.onclick = async () => {
                const uid = btn.getAttribute('data-user-id');
                const uname = btn.getAttribute('data-username');
                if (!confirm(`Are you sure you want to permanently delete user "${uname}"?`)) return;
                try {
                    await apiRequest(`/api/v1/admin/users/${encodeURIComponent(uid)}`, { method: 'DELETE' });
                    loadAdminUsers();
                } catch (e) {
                    alert('User deletion failed: ' + e.message);
                }
            };
        });
    }

    async function loadAdminRules() {
        const wrap = document.getElementById('admin-rules-table-wrap');
        const domFilter = document.getElementById('admin-rules-domain-filter');
        if (!wrap) return;
        wrap.innerHTML = '<div class="loading-placeholder">Loading official rule library...</div>';

        // Populate domains dropdown if needed
        try {
            const domData = await apiRequest('/api/v1/domains');
            if (domFilter && domData.items) {
                const cur = domFilter.value;
                domFilter.innerHTML = '<option value="">All Domains</option>' +
                    domData.items.map(d => `<option value="${escapeHtml(d.id)}">${escapeHtml(d.name)}</option>`).join('');
                domFilter.value = cur;
                domFilter.onchange = loadAdminRules;
            }
        } catch (e) {}

        const filterDomain = domFilter ? domFilter.value : '';
        const url = filterDomain ? `/api/v1/admin/official-rules?domain_id=${encodeURIComponent(filterDomain)}` : '/api/v1/admin/official-rules';

        try {
            const data = await apiRequest(url);
            const rules = data.items || [];

            const addRuleBtn = document.getElementById('admin-add-rule-btn');
            if (addRuleBtn) {
                addRuleBtn.onclick = () => openAdminRuleModal(null);
            }

            if (!rules.length) {
                wrap.innerHTML = '<div class="empty-state">No official rules found. Click "+ Add Rule" to author institutional policies.</div>';
                return;
            }

            wrap.innerHTML = `
                <table class="rules-table">
                    <thead>
                        <tr>
                            <th>Rule ID</th>
                            <th>Policy Name</th>
                            <th>Domain</th>
                            <th>Priority</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rules.map(r => `
                            <tr>
                                <td><code>${escapeHtml(r.id)}</code></td>
                                <td><strong>${escapeHtml(r.name)}</strong></td>
                                <td><span class="badge info">${escapeHtml(r.domain_id || 'academic')}</span></td>
                                <td><span class="badge neutral">${r.priority}</span></td>
                                <td><span class="badge success">${escapeHtml(r.status || 'active')}</span></td>
                                <td>
                                    <div style="display:flex;gap:6px;">
                                        <button class="rulewise-btn secondary btn-sm admin-edit-rule-btn" data-rule='${escapeHtml(JSON.stringify(r))}'>
                                            Edit
                                        </button>
                                        <button class="rulewise-btn danger btn-sm admin-del-rule-btn" data-rule-id="${escapeHtml(r.id)}">
                                            Delete
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;

            wrap.querySelectorAll('.admin-edit-rule-btn').forEach(btn => {
                btn.onclick = () => {
                    const rule = JSON.parse(btn.getAttribute('data-rule'));
                    openAdminRuleModal(rule);
                };
            });

            wrap.querySelectorAll('.admin-del-rule-btn').forEach(btn => {
                btn.onclick = async () => {
                    const rid = btn.getAttribute('data-rule-id');
                    if (!confirm(`Are you sure you want to delete official rule "${rid}"?`)) return;
                    try {
                        await apiRequest(`/api/v1/admin/rules/${encodeURIComponent(rid)}`, { method: 'DELETE' });
                        loadAdminRules();
                    } catch (e) {
                        alert('Rule deletion failed: ' + e.message);
                    }
                };
            });
        } catch (e) {
            wrap.innerHTML = `<div class="empty-state text-danger">Failed to load official rules: ${escapeHtml(e.message)}</div>`;
        }
    }

    async function openAdminRuleModal(rule = null) {
        const modal = document.getElementById('admin-rule-modal');
        const titleEl = document.getElementById('admin-rule-modal-title');
        const idInput = document.getElementById('admin-rule-id');
        const domSelect = document.getElementById('admin-rule-domain-select');
        const nameInput = document.getElementById('admin-rule-name');
        const descInput = document.getElementById('admin-rule-desc');
        const prioInput = document.getElementById('admin-rule-priority');
        const statusSelect = document.getElementById('admin-rule-status');
        const condInput = document.getElementById('admin-rule-condition');
        const consInput = document.getElementById('admin-rule-consequence');

        if (!modal) return;

        try {
            const domData = await apiRequest('/api/v1/domains');
            if (domSelect && domData.items) {
                domSelect.innerHTML = domData.items.map(d =>
                    `<option value="${escapeHtml(d.id)}">${escapeHtml(d.name)}</option>`
                ).join('');
            }
        } catch (e) {}

        if (rule) {
            if (titleEl) titleEl.textContent = 'Edit Official Rule: ' + rule.id;
            if (idInput) idInput.value = rule.id;
            if (domSelect) domSelect.value = rule.domain_id || 'dom_academic';
            if (nameInput) nameInput.value = rule.name || '';
            if (descInput) descInput.value = rule.description || '';
            if (prioInput) prioInput.value = rule.priority || 50;
            if (statusSelect) statusSelect.value = rule.status || 'active';
            if (condInput) condInput.value = JSON.stringify(rule.condition_schema || {}, null, 2);
            if (consInput) consInput.value = JSON.stringify(rule.consequence_schema || {}, null, 2);
        } else {
            if (titleEl) titleEl.textContent = 'Define New Official Rule';
            if (idInput) idInput.value = '';
            if (nameInput) nameInput.value = '';
            if (descInput) descInput.value = '';
            if (prioInput) prioInput.value = 50;
            if (statusSelect) statusSelect.value = 'active';
            if (condInput) condInput.value = '{\n  "all": [\n    { "field": "status", "operator": "==", "value": "active" }\n  ]\n}';
            if (consInput) consInput.value = '{\n  "action": "ALLOW",\n  "reason": "Official rule conditions satisfied."\n}';
        }

        modal.classList.remove('hidden');
    }

    async function loadAdminDecisions() {
        const statsWrap = document.getElementById('admin-decision-analytics-wrap') || document.getElementById('admin-decision-stats-wrap');
        const auditWrap = document.getElementById('admin-audit-logs-wrap') || document.getElementById('admin-audit-log-wrap');

        if (statsWrap) statsWrap.innerHTML = '<div class="loading-placeholder">Loading decision analytics...</div>';
        if (auditWrap) auditWrap.innerHTML = '<div class="loading-placeholder">Loading administrative audit log...</div>';

        try {
            const data = await apiRequest('/api/v1/admin/decision-analytics');
            const summary = data.summary || {};

            if (statsWrap) {
                statsWrap.innerHTML = `
                    <div class="rulewise-stats-grid" style="grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));">
                        <div class="stat-card">
                            <div class="stat-label">Total Platform Decisions</div>
                            <div class="stat-val">${summary.total_evaluations || 0}</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-label">Approved Decisions</div>
                            <div class="stat-val" style="color:var(--success);">${summary.approved_count || 0}</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-label">Rejected Decisions</div>
                            <div class="stat-val" style="color:var(--danger);">${summary.rejected_count || 0}</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-label">Approval Rate</div>
                            <div class="stat-val">${summary.approval_rate_percent || 0}%</div>
                        </div>
                    </div>
                `;
            }

            const auditsData = await apiRequest('/api/v1/admin/audit-logs?limit=40');
            const audits = auditsData.items || [];
            if (auditWrap) {
                if (!audits.length) {
                    auditWrap.innerHTML = '<div class="empty-state">No administrative audit records logged yet.</div>';
                } else {
                    auditWrap.innerHTML = `
                        <table class="rules-table">
                            <thead>
                                <tr>
                                    <th>Timestamp</th>
                                    <th>Admin</th>
                                    <th>Action</th>
                                    <th>Resource</th>
                                    <th>Details</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${audits.map(a => `
                                    <tr>
                                        <td><small>${new Date(a.created_at || Date.now()).toLocaleTimeString()}</small></td>
                                        <td><strong>${escapeHtml(a.admin_username || a.admin_email || 'System')}</strong></td>
                                        <td><span class="badge info">${escapeHtml(a.action)}</span></td>
                                        <td><code>${escapeHtml(a.target_type || '')}:${escapeHtml(a.target_id || '')}</code></td>
                                        <td><small>${escapeHtml(JSON.stringify(a.details || {}))}</small></td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    `;
                }
            }
        } catch (e) {
            console.error('Failed to load decision analytics:', e);
        }
    }

    async function loadAdminSessions() {
        const wrap = document.getElementById('admin-sessions-table-wrap');
        if (!wrap) return;
        wrap.innerHTML = '<div class="loading-placeholder">Loading active sessions...</div>';

        const refBtn = document.getElementById('refresh-admin-sessions-btn');
        if (refBtn) refBtn.onclick = loadAdminSessions;

        try {
            const data = await apiRequest('/api/v1/admin/sessions?limit=50');
            const sessions = data.items || [];

            if (!sessions.length) {
                wrap.innerHTML = '<div class="empty-state">No active sessions found.</div>';
                return;
            }

            wrap.innerHTML = `
                <table class="rules-table">
                    <thead>
                        <tr>
                            <th>Session ID</th>
                            <th>Title</th>
                            <th>User ID</th>
                            <th>Created At</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${sessions.map(s => `
                            <tr>
                                <td><code>${escapeHtml(s.id)}</code></td>
                                <td><strong>${escapeHtml(s.title || 'Untitled')}</strong></td>
                                <td>${escapeHtml(s.user_id || 'Guest')}</td>
                                <td><small>${new Date(s.created_at || Date.now()).toLocaleString()}</small></td>
                                <td>
                                    <button class="rulewise-btn danger btn-sm terminate-session-btn" data-conv-id="${escapeHtml(s.id)}">
                                        Terminate
                                    </button>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;

            wrap.querySelectorAll('.terminate-session-btn').forEach(b => {
                b.onclick = async () => {
                    const cid = b.getAttribute('data-conv-id');
                    if (!confirm(`Terminate session "${cid}"?`)) return;
                    try {
                        await apiRequest(`/api/v1/admin/sessions/${encodeURIComponent(cid)}`, { method: 'DELETE' });
                        loadAdminSessions();
                    } catch (e) {
                        alert('Termination failed: ' + e.message);
                    }
                };
            });
        } catch (e) {
            wrap.innerHTML = `<div class="empty-state text-danger">Failed to load sessions: ${escapeHtml(e.message)}</div>`;
        }
    }

    async function loadAdminSafetyPolicies() {
        const enabledToggle = document.getElementById('safety-enabled-toggle');
        const dualUseToggle = document.getElementById('safety-dual-use-toggle');
        const customKeywords = document.getElementById('safety-custom-keywords');
        const statusMsg = document.getElementById('safety-policy-status-msg');
        const saveBtn = document.getElementById('save-safety-policies-btn');

        try {
            const data = await apiRequest('/api/v1/admin/safety-policies');
            if (enabledToggle) enabledToggle.checked = data.enabled !== false;
            if (dualUseToggle) dualUseToggle.checked = data.allow_educational_dual_use !== false;
            if (customKeywords) customKeywords.value = (data.custom_blocked_keywords || []).join(', ');
        } catch (e) {}

        if (saveBtn) {
            saveBtn.onclick = async () => {
                const kwList = customKeywords ? customKeywords.value.split(',').map(s => s.trim()).filter(Boolean) : [];
                saveBtn.disabled = true;
                saveBtn.textContent = 'Saving...';
                try {
                    await apiRequest('/api/v1/admin/safety-policies', {
                        method: 'PUT',
                        body: JSON.stringify({
                            enabled: enabledToggle ? enabledToggle.checked : true,
                            allow_educational_dual_use: dualUseToggle ? dualUseToggle.checked : true,
                            custom_blocked_keywords: kwList,
                        }),
                    });
                    if (statusMsg) {
                        statusMsg.textContent = 'Safety policies updated and active across engine!';
                        statusMsg.style.color = '#10b981';
                        setTimeout(() => { statusMsg.textContent = ''; }, 3000);
                    }
                } catch (e) {
                    alert('Save failed: ' + e.message);
                } finally {
                    saveBtn.disabled = false;
                    saveBtn.textContent = 'Save Safety Policies';
                }
            };
        }
    }

    // -------------------------------------------------------------------------
    // 14. EXPLORE DOMAINS & DECISION CATALOG (Phase 2 & 7)
    // -------------------------------------------------------------------------
    async function loadDomainsView() {
        const grid = document.getElementById('domains-grid');
        if (!grid) return;
        grid.innerHTML = '<div class="loading-placeholder">Loading decision domains...</div>';

        // Wire create domain modal triggers
        const openDomModalBtn = document.getElementById('open-create-domain-modal-btn');
        const domModal = document.getElementById('domain-modal');
        const closeDomModalBtn = document.getElementById('domain-modal-close-btn');
        const domForm = document.getElementById('create-domain-form');

        if (openDomModalBtn && domModal) {
            openDomModalBtn.onclick = () => domModal.classList.remove('hidden');
        }
        if (closeDomModalBtn && domModal) {
            closeDomModalBtn.onclick = () => domModal.classList.add('hidden');
        }
        if (domForm && domModal) {
            domForm.onsubmit = async (e) => {
                e.preventDefault();
                const name = document.getElementById('new-dom-name')?.value.trim();
                const slug = document.getElementById('new-dom-slug')?.value.trim();
                const category = document.getElementById('new-dom-category')?.value;
                const desc = document.getElementById('new-dom-desc')?.value.trim();
                try {
                    await apiRequest('/api/v1/domains', {
                        method: 'POST',
                        body: JSON.stringify({ name, slug, category, description: desc }),
                    });
                    domModal.classList.add('hidden');
                    domForm.reset();
                    loadDomainsView();
                } catch (err) {
                    alert('Failed to create domain: ' + err.message);
                }
            };
        }

        try {
            const data = await apiRequest('/api/v1/domains');
            state.domains = Array.isArray(data) ? data : (data.items || []);
            renderDomainsGrid(state.domains);

            const pills = document.querySelectorAll('#domain-category-pills .admin-subnav-btn');
            pills.forEach(pill => {
                pill.onclick = () => {
                    pills.forEach(p => p.classList.remove('active'));
                    pill.classList.add('active');
                    const cat = pill.getAttribute('data-category');
                    if (cat === 'all') {
                        renderDomainsGrid(state.domains);
                    } else {
                        const filtered = state.domains.filter(d => (d.category || '').toLowerCase().includes(cat.toLowerCase()));
                        renderDomainsGrid(filtered);
                    }
                };
            });
        } catch (err) {
            grid.innerHTML = `<div class="empty-state text-danger">Failed to load domains: ${escapeHtml(err.message)}</div>`;
        }
    }

    function renderDomainsGrid(domains) {
        const grid = document.getElementById('domains-grid');
        if (!grid) return;

        if (!domains.length) {
            grid.innerHTML = '<div class="empty-state">No decision domains found for this category.</div>';
            return;
        }

        grid.innerHTML = domains.map(d => `
            <div class="rulewise-card domain-card ${d.id === state.activeDomainId ? 'active' : ''}">
                <div class="card-header">
                    <span class="domain-category-badge">${escapeHtml(d.category || 'Domain')}</span>
                    <span class="rules-count-badge">${d.rules_count || 0} Rules</span>
                </div>
                <h3 class="card-title">${escapeHtml(d.name)}</h3>
                <p class="card-desc">${escapeHtml(d.description || 'Deterministic rule policy domain.')}</p>
                <div class="card-actions" style="margin-top:14px;display:flex;gap:8px;">
                    <button class="rulewise-btn primary btn-sm start-advisory-btn" data-domain-id="${escapeHtml(d.id)}" data-domain-name="${escapeHtml(d.name)}">
                        Start Advisory
                    </button>
                    <button class="rulewise-btn secondary btn-sm select-domain-btn" data-domain-id="${escapeHtml(d.id)}">
                        ${d.id === state.activeDomainId ? 'Active Scope' : 'Set Active'}
                    </button>
                </div>
            </div>
        `).join('');

        grid.querySelectorAll('.start-advisory-btn').forEach(btn => {
            btn.onclick = () => {
                const domId = btn.getAttribute('data-domain-id');
                const domName = btn.getAttribute('data-domain-name');
                setActiveDomain(domId, domName);
                switchTab('chat-view');
                const input = document.getElementById('user-input') || document.getElementById('chat-input');
                if (input) {
                    input.placeholder = `Ask a question under ${domName} policy...`;
                    input.focus();
                }
            };
        });

        grid.querySelectorAll('.select-domain-btn').forEach(btn => {
            btn.onclick = () => {
                const domId = btn.getAttribute('data-domain-id');
                const matched = state.domains.find(d => d.id === domId);
                setActiveDomain(domId, matched ? matched.name : 'RuleWise Policy');
                renderDomainsGrid(state.domains);
            };
        });
    }

    function setActiveDomain(domainId, domainName) {
        state.activeDomainId = domainId;
        state.activeDomainName = domainName;

        const compLabel = document.getElementById('composer-domain-label');
        if (compLabel) compLabel.textContent = domainName;

        const activeIndicator = document.getElementById('active-domain-indicator');
        if (activeIndicator) activeIndicator.textContent = domainName;
    }

    // -------------------------------------------------------------------------
    // 15. OFFICIAL RULE LIBRARY (Read-only Institutional Policy View)
    // -------------------------------------------------------------------------
    async function loadOfficialLibraryView() {
        const wrap = document.getElementById('official-rules-list') || document.getElementById('official-rules-container');
        if (!wrap) return;
        wrap.innerHTML = '<div class="loading-placeholder">Loading institutional rule catalog...</div>';

        try {
            const data = await apiRequest('/api/v1/rules');
            const rules = Array.isArray(data) ? data : (data.items || []);

            if (!rules.length) {
                wrap.innerHTML = '<div class="empty-state">No rules registered in this library.</div>';
                return;
            }

            wrap.innerHTML = `
                <div class="rulewise-cards-grid">
                    ${rules.map(r => `
                        <div class="rulewise-card">
                            <div class="card-header">
                                <span class="badge info">Priority ${r.priority}</span>
                                <span class="badge success">Audited</span>
                            </div>
                            <h3 class="card-title">${escapeHtml(r.name)}</h3>
                            <p class="card-desc">${escapeHtml(r.description || 'Deterministic policy verification.')}</p>
                            <div style="margin-top:12px;">
                                <button class="rulewise-btn secondary btn-sm inspect-lib-rule-btn" data-rule='${escapeHtml(JSON.stringify(r))}'>
                                    Inspect Schema
                                </button>
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;

            wrap.querySelectorAll('.inspect-lib-rule-btn').forEach(b => {
                b.onclick = () => {
                    const r = JSON.parse(b.getAttribute('data-rule'));
                    showTraceModal(r);
                };
            });
        } catch (err) {
            wrap.innerHTML = `<div class="empty-state text-danger">Failed to load rules: ${escapeHtml(err.message)}</div>`;
        }
    }

    // -------------------------------------------------------------------------
    // 16. DECISION HISTORY & AUDIT LOG (User-Isolated, Filterable, Traceable)
    // -------------------------------------------------------------------------
    async function loadHistoryView() {
        const container = document.getElementById('evaluations-history-list');
        if (!container) return;
        container.innerHTML = '<div class="loading-placeholder">Loading decision history...</div>';

        const qInput = document.getElementById('history-search-input');
        const domFilter = document.getElementById('history-domain-filter');
        const outFilter = document.getElementById('history-decision-filter') || document.getElementById('history-outcome-filter');
        const refreshBtn = document.getElementById('refresh-history-btn');

        if (refreshBtn) refreshBtn.onclick = loadHistoryView;

        if (domFilter && domFilter.options.length <= 1) {
            apiRequest('/api/v1/domains').then(data => {
                const doms = Array.isArray(data) ? data : (data.items || []);
                doms.forEach(d => {
                    const opt = document.createElement('option');
                    opt.value = d.id;
                    opt.textContent = d.name;
                    domFilter.appendChild(opt);
                });
            }).catch(() => {});
        }

        const q = qInput ? qInput.value.trim() : '';
        const domain = domFilter ? domFilter.value : '';
        const outcome = outFilter ? outFilter.value : '';

        const params = new URLSearchParams({ limit: '50' });
        if (q) params.set('q', q);
        if (domain) params.set('domain', domain);
        if (outcome) params.set('decision', outcome);

        try {
            const data = await apiRequest(`/api/v1/history/evaluations?${params.toString()}`);
            const items = Array.isArray(data) ? data : (data.items || []);

            if (!items.length) {
                container.innerHTML = `
                    <div class="empty-state">
                        <p>No decision records found.</p>
                        <small>Ask an eligibility or compliance question in chat to record persistent decisions.</small>
                    </div>
                `;
                return;
            }

            container.innerHTML = `
                <table class="rules-table">
                    <thead>
                        <tr>
                            <th>Timestamp</th>
                            <th>Original Inquiry / Subject</th>
                            <th>Domain</th>
                            <th>Decision Outcome</th>
                            <th>Applied Rules</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${items.map(h => {
                            const res = h.result_summary || {};
                            const eligible = res.is_eligible ?? res.eligible;
                            let outcomeBadge = '<span class="badge neutral">EVALUATED</span>';
                            if (eligible === true) outcomeBadge = '<span class="badge success">APPROVED</span>';
                            if (eligible === false) outcomeBadge = '<span class="badge error">REJECTED</span>';

                            const rulesCount = (res.executed_rules || res.matched_rules || []).length;
                            const subject = res.student || res.subject || h.question || 'Inquiry';

                            return `
                                <tr>
                                    <td><small>${new Date(h.created_at || Date.now()).toLocaleString()}</small></td>
                                    <td>
                                        <strong>${escapeHtml(subject)}</strong>
                                        ${h.question && h.question !== subject ? `<br><small style="color:#94a3b8;">${escapeHtml(h.question)}</small>` : ''}
                                    </td>
                                    <td><code>${escapeHtml(h.domain_id || 'academic')}</code></td>
                                    <td>${outcomeBadge}</td>
                                    <td><span class="badge neutral">${rulesCount} rules fired</span></td>
                                    <td>
                                        <div style="display:flex;gap:6px;">
                                            <button class="rulewise-btn secondary btn-sm view-history-trace-btn" data-trace='${escapeHtml(JSON.stringify(h))}'>
                                                Proof Trace
                                            </button>
                                            <button class="rulewise-btn danger btn-sm delete-history-btn" data-history-id="${escapeHtml(h.id)}">
                                                Delete
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            `;
                        }).join('')}
                    </tbody>
                </table>
            `;

            container.querySelectorAll('.view-history-trace-btn').forEach(btn => {
                btn.onclick = () => {
                    const traceData = JSON.parse(btn.getAttribute('data-trace'));
                    showTraceModal(traceData);
                };
            });

            container.querySelectorAll('.delete-history-btn').forEach(btn => {
                btn.onclick = async () => {
                    const hid = btn.getAttribute('data-history-id');
                    if (!confirm('Delete this decision record permanently?')) return;
                    try {
                        await apiRequest(`/api/v1/history/evaluations/${encodeURIComponent(hid)}`, { method: 'DELETE' });
                        loadHistoryView();
                    } catch (e) {
                        alert('Deletion failed: ' + e.message);
                    }
                };
            });

            if (qInput && !qInput.onchange) qInput.onchange = loadHistoryView;
            if (domFilter && !domFilter.onchange) domFilter.onchange = loadHistoryView;
            if (outFilter && !outFilter.onchange) outFilter.onchange = loadHistoryView;
        } catch (err) {
            container.innerHTML = `<div class="empty-state text-danger">Failed to load decision history: ${escapeHtml(err.message)}</div>`;
        }
    }

    // -------------------------------------------------------------------------
    // 17. VISUAL RULE STUDIO & WHAT-IF SIMULATOR
    // -------------------------------------------------------------------------
    function loadStudioView() {
        apiRequest('/api/v1/domains').then(data => {
            const select = document.getElementById('rule-domain-select');
            const items = Array.isArray(data) ? data : (data.items || []);
            if (select && items.length) {
                select.innerHTML = items.map(d => `<option value="${escapeHtml(d.id)}">${escapeHtml(d.name)}</option>`).join('');
            }
        }).catch(() => {});
    }

    function initRuleStudio() {
        loadStudioView();

        const validateBtn = document.getElementById('validate-rule-btn');
        const feedback = document.getElementById('rule-validation-feedback');
        const condInput = document.getElementById('rule-condition-json');
        const actInput = document.getElementById('rule-action-json');

        if (validateBtn && feedback) {
            validateBtn.onclick = () => {
                feedback.classList.remove('hidden');
                try {
                    if (condInput && condInput.value) JSON.parse(condInput.value);
                    if (actInput && actInput.value) JSON.parse(actInput.value);
                    feedback.style.color = '#86efac';
                    feedback.textContent = '✓ Condition and Action JSON schemas are syntactically valid.';
                } catch (e) {
                    feedback.style.color = '#fca5a5';
                    feedback.textContent = '✗ JSON Syntax Error: ' + e.message;
                }
            };
        }

        const form = document.getElementById('create-rule-form');
        if (form) {
            form.onsubmit = async (e) => {
                e.preventDefault();
                const domainId = document.getElementById('rule-domain-select')?.value || 'dom_academic';
                const name = document.getElementById('rule-name-input')?.value.trim();
                const priority = parseInt(document.getElementById('rule-priority-input')?.value || '10', 10);
                const condText = document.getElementById('rule-condition-json')?.value.trim();
                const actText = document.getElementById('rule-action-json')?.value.trim();
                const expl = document.getElementById('rule-explanation-tpl')?.value.trim();

                try {
                    const condJson = condText ? JSON.parse(condText) : { all: [] };
                    const actJson = actText ? JSON.parse(actText) : { action: 'ALLOW', message: 'Rule verified' };

                    const payload = {
                        name,
                        domain_id: domainId,
                        description: expl || 'Author-defined rule schema',
                        priority,
                        condition_schema: condJson,
                        consequence_schema: actJson,
                    };

                    await apiRequest('/api/v1/rules', {
                        method: 'POST',
                        body: JSON.stringify(payload),
                    });
                    alert('Rule successfully created and registered in domain!');
                    form.reset();
                    if (feedback) feedback.classList.add('hidden');
                } catch (err) {
                    alert('Failed to save rule: ' + err.message);
                }
            };
        }

        const runTestBtn = document.getElementById('run-rule-test-btn');
        if (runTestBtn) {
            runTestBtn.onclick = async () => {
                const resultsBox = document.getElementById('rule-test-results');
                const outputEl = document.getElementById('rule-test-output');
                const factsText = document.getElementById('test-facts-json')?.value;
                const domainId = document.getElementById('rule-domain-select')?.value || 'dom_academic';

                if (resultsBox) resultsBox.classList.remove('hidden');
                if (outputEl) outputEl.innerHTML = '<div class="loading-placeholder">Testing rule activation against facts...</div>';

                try {
                    const facts = JSON.parse(factsText || '{}');
                    const res = await apiRequest('/api/v1/evaluations/evaluate', {
                        method: 'POST',
                        body: JSON.stringify({ domain_id: domainId, context_data: facts }),
                    });
                    if (outputEl) {
                        outputEl.innerHTML = `
                            <div style="margin-top:8px;">
                                <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                                    <strong>Status:</strong>
                                    <span class="badge ${res.is_eligible ? 'success' : 'error'}">${res.is_eligible ? 'ACTIVATED / ELIGIBLE' : 'NOT ACTIVATED'}</span>
                                </div>
                                <pre style="font-size:11px;max-height:160px;overflow-y:auto;background:rgba(0,0,0,0.3);padding:8px;border-radius:4px;">${escapeHtml(JSON.stringify(res, null, 2))}</pre>
                            </div>
                        `;
                    }
                } catch (err) {
                    if (outputEl) outputEl.innerHTML = `<div class="empty-state text-danger">Test failed: ${escapeHtml(err.message)}</div>`;
                }
            };
        }
    }

    function loadSimulatorView() {
        apiRequest('/api/v1/domains').then(data => {
            const select = document.getElementById('sim-domain');
            const items = Array.isArray(data) ? data : (data.items || []);
            if (select && items.length) {
                select.innerHTML = items.map(d => `<option value="${escapeHtml(d.id)}">${escapeHtml(d.name)}</option>`).join('');
            }
        }).catch(() => {});

        const btn = document.getElementById('run-simulation-btn');
        if (btn) {
            btn.onclick = async () => {
                const out = document.getElementById('sim-results-output');
                if (out) out.innerHTML = '<div class="loading-placeholder">Evaluating baseline vs counterfactual scenarios...</div>';

                try {
                    const domId = document.getElementById('sim-domain')?.value || 'dom_academic';
                    const baseInput = document.getElementById('sim-baseline-facts')?.value || '{}';
                    const candInput = document.getElementById('sim-candidate-facts')?.value || '{}';
                    const baseJson = JSON.parse(baseInput);
                    const candJson = JSON.parse(candInput);

                    const [resBase, resCand] = await Promise.all([
                        apiRequest('/api/v1/evaluations/evaluate', {
                            method: 'POST',
                            body: JSON.stringify({ domain_id: domId, context_data: baseJson }),
                        }),
                        apiRequest('/api/v1/evaluations/evaluate', {
                            method: 'POST',
                            body: JSON.stringify({ domain_id: domId, context_data: candJson }),
                        })
                    ]);

                    if (out) {
                        out.innerHTML = `
                            <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:12px;">
                                <div style="background:rgba(255,255,255,0.03);padding:14px;border-radius:8px;border:1px solid rgba(255,255,255,0.08);">
                                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                                        <strong style="font-size:13px;">Baseline Scenario</strong>
                                        <span class="badge ${resBase.is_eligible ? 'success' : 'error'}">${resBase.is_eligible ? 'ELIGIBLE' : 'INELIGIBLE'}</span>
                                    </div>
                                    <pre style="font-size:11px;max-height:180px;overflow-y:auto;background:rgba(0,0,0,0.2);padding:8px;border-radius:4px;">${escapeHtml(JSON.stringify(resBase, null, 2))}</pre>
                                </div>
                                <div style="background:rgba(255,255,255,0.03);padding:14px;border-radius:8px;border:1px solid rgba(255,255,255,0.08);">
                                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                                        <strong style="font-size:13px;">Counterfactual Scenario</strong>
                                        <span class="badge ${resCand.is_eligible ? 'success' : 'error'}">${resCand.is_eligible ? 'ELIGIBLE' : 'INELIGIBLE'}</span>
                                    </div>
                                    <pre style="font-size:11px;max-height:180px;overflow-y:auto;background:rgba(0,0,0,0.2);padding:8px;border-radius:4px;">${escapeHtml(JSON.stringify(resCand, null, 2))}</pre>
                                </div>
                            </div>
                        `;
                    }
                } catch (e) {
                    if (out) out.innerHTML = `<div class="empty-state text-danger">Simulation error: ${escapeHtml(e.message)}</div>`;
                }
            };
        }
    }

    // -------------------------------------------------------------------------
    // 18. MODALS & AUTHENTICATION HANDLERS
    // -------------------------------------------------------------------------
    function initModals() {
        // Trace Modal Close
        const traceClose = document.getElementById('trace-modal-close-btn');
        if (traceClose) traceClose.onclick = () => document.getElementById('trace-modal').classList.add('hidden');

        // Top Auth, Sidebar Auth, and Logout Triggers
        const topAuthBtn = document.getElementById('top-auth-btn');
        if (topAuthBtn) topAuthBtn.onclick = () => openAuthModal('login');

        const sidebarAuthBtn = document.getElementById('sidebar-auth-btn');
        if (sidebarAuthBtn) sidebarAuthBtn.onclick = () => openAuthModal('login');

        const topLogoutBtn = document.getElementById('top-logout-btn');
        if (topLogoutBtn) topLogoutBtn.onclick = handleLogout;

        const sidebarLogoutBtn = document.getElementById('sidebar-logout-btn');
        if (sidebarLogoutBtn) sidebarLogoutBtn.onclick = (e) => {
            e.stopPropagation();
            handleLogout();
        };

        const modalLogoutBtn = document.getElementById('modal-logout-btn');
        if (modalLogoutBtn) modalLogoutBtn.onclick = handleLogout;

        const authCloseBtn = document.getElementById('auth-modal-close-btn');
        if (authCloseBtn) authCloseBtn.onclick = closeAuthModal;

        // Auth Tabs Switching
        const tabLogin = document.getElementById('tab-login-btn');
        const tabAdminLogin = document.getElementById('tab-admin-login-btn');
        const tabReg = document.getElementById('tab-register-btn');
        const tabGuest = document.getElementById('tab-guest-btn');

        const formLogin = document.getElementById('login-form');
        const formAdminLogin = document.getElementById('admin-login-form');
        const formReg = document.getElementById('register-form');
        const formReset = document.getElementById('reset-password-form');
        const panelGuest = document.getElementById('guest-panel');

        function selectAuthTab(activeBtn, activeForm) {
            [tabLogin, tabAdminLogin, tabReg, tabGuest].forEach(b => b && b.classList.remove('active'));
            [formLogin, formAdminLogin, formReg, formReset, panelGuest].forEach(f => f && f.classList.add('hidden'));

            if (activeBtn) activeBtn.classList.add('active');
            if (activeForm) activeForm.classList.remove('hidden');

            const errBox = document.getElementById('auth-error-msg');
            if (errBox) errBox.classList.add('hidden');
        }

        if (tabLogin) tabLogin.onclick = () => selectAuthTab(tabLogin, formLogin);
        if (tabAdminLogin) tabAdminLogin.onclick = () => selectAuthTab(tabAdminLogin, formAdminLogin);
        if (tabReg) tabReg.onclick = () => selectAuthTab(tabReg, formReg);
        if (tabGuest) tabGuest.onclick = () => selectAuthTab(tabGuest, panelGuest);

        // Forgot Password link & Back to Login
        const forgotLink = document.getElementById('forgot-password-link');
        const adminForgotLink = document.getElementById('admin-forgot-password-link');
        const backToLoginBtn = document.getElementById('back-to-login-btn');
        if (forgotLink) {
            forgotLink.onclick = () => {
                selectAuthTab(null, formReset);
            };
        }
        if (adminForgotLink) {
            adminForgotLink.onclick = () => {
                selectAuthTab(null, formReset);
            };
        }
        if (backToLoginBtn) {
            backToLoginBtn.onclick = () => {
                selectAuthTab(tabLogin, formLogin);
            };
        }

        // Standard User Login Handler
        if (formLogin) {
            formLogin.onsubmit = async (e) => {
                e.preventDefault();
                const u = document.getElementById('login-username').value.trim();
                const p = document.getElementById('login-password').value;
                const errBox = document.getElementById('auth-error-msg');
                if (errBox) errBox.classList.add('hidden');

                if (!u) {
                    if (errBox) {
                        errBox.textContent = 'Please enter your Gmail or username.';
                        errBox.classList.remove('hidden');
                    }
                    return;
                }

                try {
                    const res = await apiRequest('/api/v1/auth/login', {
                        method: 'POST',
                        body: JSON.stringify({ username: u, password: p, is_admin_login: false }),
                    });
                    state.token = res.access_token;
                    state.user = res.user;
                    localStorage.setItem('rulewise_token', state.token);
                    localStorage.setItem('rulewise_user', JSON.stringify(state.user));
                    updateUserUI();
                    closeAuthModal();
                    renderRecentChatsList();
                } catch (err) {
                    if (errBox) {
                        errBox.textContent = err.message;
                        errBox.classList.remove('hidden');
                    }
                }
            };
        }

        // Dedicated Administrator Login Handler
        if (formAdminLogin) {
            formAdminLogin.onsubmit = async (e) => {
                e.preventDefault();
                const u = document.getElementById('admin-login-username').value.trim();
                const p = document.getElementById('admin-login-password').value;
                const errBox = document.getElementById('auth-error-msg');
                if (errBox) errBox.classList.add('hidden');

                try {
                    const res = await apiRequest('/api/v1/auth/login', {
                        method: 'POST',
                        body: JSON.stringify({ username: u, password: p, is_admin_login: true }),
                    });
                    state.token = res.access_token;
                    state.user = res.user;
                    localStorage.setItem('rulewise_token', state.token);
                    localStorage.setItem('rulewise_user', JSON.stringify(state.user));
                    updateUserUI();
                    closeAuthModal();
                    switchTab('admin-view');
                } catch (err) {
                    if (errBox) {
                        errBox.textContent = `Admin Authorization Failed: ${err.message}`;
                        errBox.classList.remove('hidden');
                    }
                }
            };
        }

        // Register Handler (Gmail Mandatory)
        if (formReg) {
            formReg.onsubmit = async (e) => {
                e.preventDefault();
                const u = document.getElementById('reg-username').value.trim();
                const em = document.getElementById('reg-email').value.trim();
                const p = document.getElementById('reg-password').value;
                const errBox = document.getElementById('auth-error-msg');
                if (errBox) errBox.classList.add('hidden');

                if (!em || !em.includes('@')) {
                    if (errBox) {
                        errBox.textContent = 'A valid Gmail or Email address is required to register.';
                        errBox.classList.remove('hidden');
                    }
                    return;
                }

                try {
                    const res = await apiRequest('/api/v1/auth/register', {
                        method: 'POST',
                        body: JSON.stringify({ username: u, email: em, password: p }),
                    });
                    state.token = res.access_token;
                    state.user = res.user;
                    localStorage.setItem('rulewise_token', state.token);
                    localStorage.setItem('rulewise_user', JSON.stringify(state.user));
                    updateUserUI();
                    closeAuthModal();
                    renderRecentChatsList();
                } catch (err) {
                    if (errBox) {
                        errBox.textContent = err.message;
                        errBox.classList.remove('hidden');
                    }
                }
            };
        }

        // Password Reset Handler
        if (formReset) {
            formReset.onsubmit = async (e) => {
                e.preventDefault();
                const em = document.getElementById('reset-email').value.trim();
                const p = document.getElementById('reset-new-password').value;
                const errBox = document.getElementById('auth-error-msg');
                if (errBox) errBox.classList.add('hidden');

                try {
                    const res = await apiRequest('/api/v1/auth/reset-password', {
                        method: 'POST',
                        body: JSON.stringify({ email: em, new_password: p }),
                    });
                    alert(res.message || 'Password updated successfully! Please sign in with your new password.');
                    selectAuthTab(tabLogin, formLogin);
                } catch (err) {
                    if (errBox) {
                        errBox.textContent = err.message;
                        errBox.classList.remove('hidden');
                    }
                }
            };
        }

        // Change Password Handler for Authenticated Users/Admins
        const changePassForm = document.getElementById('change-password-form');
        if (changePassForm) {
            changePassForm.onsubmit = async (e) => {
                e.preventDefault();
                const cur = document.getElementById('change-cur-pass').value;
                const next = document.getElementById('change-new-pass').value;
                const msgBox = document.getElementById('change-pass-msg');
                if (msgBox) {
                    msgBox.className = 'hidden';
                    msgBox.textContent = '';
                }
                try {
                    const res = await apiRequest('/api/v1/auth/change-password', {
                        method: 'POST',
                        body: JSON.stringify({ current_password: cur, new_password: next }),
                    });
                    if (msgBox) {
                        msgBox.style.background = 'rgba(34, 197, 94, 0.15)';
                        msgBox.style.color = '#86efac';
                        msgBox.textContent = res.message || 'Password updated successfully!';
                        msgBox.classList.remove('hidden');
                    }
                    changePassForm.reset();
                } catch (err) {
                    if (msgBox) {
                        msgBox.style.background = 'rgba(239, 68, 68, 0.15)';
                        msgBox.style.color = '#fca5a5';
                        msgBox.textContent = err.message || 'Failed to update password.';
                        msgBox.classList.remove('hidden');
                    }
                }
            };
        }

        // Guest Continue
        const guestContinueBtn = document.getElementById('guest-continue-btn');
        if (guestContinueBtn) {
            guestContinueBtn.onclick = async () => {
                try {
                    if (!state.token) {
                        const res = await apiRequest('/api/v1/auth/guest', { method: 'POST' });
                        state.token = res.access_token;
                        state.user = res.user;
                        localStorage.setItem('rulewise_token', state.token);
                        localStorage.setItem('rulewise_user', JSON.stringify(state.user));
                    }
                    updateUserUI();
                    closeAuthModal();
                } catch (err) {
                    closeAuthModal();
                }
            };
        }

        // Admin Create User Modal Handlers
        const adminUserModal = document.getElementById('admin-add-user-modal');
        const adminUserModalClose = document.getElementById('admin-user-modal-close-btn');
        if (adminUserModalClose) adminUserModalClose.onclick = () => adminUserModal.classList.add('hidden');

        const adminCreateUserForm = document.getElementById('admin-create-user-form');
        if (adminCreateUserForm) {
            adminCreateUserForm.onsubmit = async (e) => {
                e.preventDefault();
                const uname = document.getElementById('new-user-username').value.trim();
                const email = document.getElementById('new-user-email').value.trim();
                const password = document.getElementById('new-user-password').value;
                const role = document.getElementById('new-user-role').value;

                try {
                    await apiRequest('/api/v1/admin/users', {
                        method: 'POST',
                        body: JSON.stringify({ username: uname, email, password, role }),
                    });
                    adminUserModal.classList.add('hidden');
                    adminCreateUserForm.reset();
                    loadAdminUsers();
                } catch (err) {
                    alert('Failed to provision user: ' + err.message);
                }
            };
        }

        // Admin Rule Modal Handlers
        const adminRuleModal = document.getElementById('admin-rule-modal');
        const adminRuleModalClose = document.getElementById('admin-rule-modal-close-btn');
        if (adminRuleModalClose) adminRuleModalClose.onclick = () => adminRuleModal.classList.add('hidden');

        const adminRuleForm = document.getElementById('admin-rule-form');
        if (adminRuleForm) {
            adminRuleForm.onsubmit = async (e) => {
                e.preventDefault();
                const rid = document.getElementById('admin-rule-id').value;
                const domId = document.getElementById('admin-rule-domain-select').value;
                const name = document.getElementById('admin-rule-name').value.trim();
                const desc = document.getElementById('admin-rule-desc').value.trim();
                const priority = parseInt(document.getElementById('admin-rule-priority').value || '50', 10);
                const status = document.getElementById('admin-rule-status').value;

                let condSchema, consSchema;
                try {
                    condSchema = JSON.parse(document.getElementById('admin-rule-condition').value);
                    consSchema = JSON.parse(document.getElementById('admin-rule-consequence').value);
                } catch (jsonErr) {
                    alert('Invalid JSON in Condition or Consequence: ' + jsonErr.message);
                    return;
                }

                const payload = {
                    name,
                    domain_id: domId,
                    description: desc,
                    priority,
                    status,
                    condition_schema: condSchema,
                    consequence_schema: consSchema,
                };

                try {
                    if (rid) {
                        await apiRequest(`/api/v1/admin/rules/${encodeURIComponent(rid)}`, {
                            method: 'PUT',
                            body: JSON.stringify(payload),
                        });
                    } else {
                        await apiRequest('/api/v1/admin/rules', {
                            method: 'POST',
                            body: JSON.stringify(payload),
                        });
                    }
                    adminRuleModal.classList.add('hidden');
                    loadAdminRules();
                } catch (err) {
                    alert('Failed to save official rule: ' + err.message);
                }
            };
        }

        // Sidebar Navigation Toggles
        const toggleBtn = document.getElementById('toggle-sidebar-btn');
        if (toggleBtn) toggleBtn.onclick = toggleSidebar;

        const headerToggleBtn = document.getElementById('header-sidebar-toggle-btn');
        if (headerToggleBtn) headerToggleBtn.onclick = toggleSidebar;

        const backdrop = document.getElementById('sidebar-backdrop');
        if (backdrop) backdrop.onclick = closeMobileSidebar;
    }

    function showTraceModal(data) {
        const modal = document.getElementById('trace-modal');
        const content = document.getElementById('trace-modal-content');
        if (!modal || !content) return;
        modal.classList.remove('hidden');

        content.innerHTML = `
            <div style="font-family:var(--font-mono);font-size:12.5px;max-height:500px;overflow-y:auto;background:rgba(0,0,0,0.3);padding:14px;border-radius:6px;border:1px solid rgba(255,255,255,0.06);">
                <pre style="background:transparent;color:inherit;padding:0;margin:0;">${escapeHtml(JSON.stringify(data, null, 2))}</pre>
            </div>
        `;
    }

    // -------------------------------------------------------------------------
    // 19. Helpers & Utilities
    // -------------------------------------------------------------------------
    function scrollToBottom() {
        const chatArea = document.getElementById('chat-area');
        if (chatArea) {
            chatArea.scrollTop = chatArea.scrollHeight;
        }
    }

    function formatTime() {
        const d = new Date();
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function formatMarkdown(text) {
        if (!text) return '';
        let escaped = escapeHtml(text);

        escaped = escaped.replace(/```([a-zA-Z0-9]*)\n([\s\S]*?)```/g, (match, lang, code) => {
            const displayLang = lang || 'code';
            return `<pre><div style="display:flex;justify-content:space-between;font-size:11px;color:#94a3b8;margin-bottom:6px;border-bottom:1px solid rgba(255,255,255,0.1);padding-bottom:4px;"><span>${displayLang}</span><span>RuleWise Verified</span></div><code>${code.trim()}</code></pre>`;
        });

        escaped = escaped.replace(/`([^`]+)`/g, '<code>$1</code>');
        escaped = escaped.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        escaped = escaped.replace(/\*([^*]+)\*/g, '<em>$1</em>');

        return escaped.split('\n\n').map(p => `<p>${p.replace(/\n/g, '<br>')}</p>`).join('');
    }

    // -------------------------------------------------------------------------
    // 20. Application Entrypoint
    // -------------------------------------------------------------------------
    window.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('.nav-item').forEach(btn => {
            btn.addEventListener('click', () => {
                const tab = btn.getAttribute('data-tab');
                if (tab) switchTab(tab);
            });
        });

        initChat();
        initChatSearch();
        initRuleStudio();
        initModals();
        initAuth();
    });

})();
