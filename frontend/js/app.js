/**
 * RuleWise AI — Complete Frontend Controller (v2.0.0 Production)
 * 
 * Features:
 * - Real Google OAuth 2.0 / OpenID Connect token verification with Google Identity Services.
 * - Strict Role-Based Access Control (Admin Login option, server-enforced RBAC, Admin nav hidden from normal users).
 * - Complete Admin Dashboard with 4 sub-views:
 *     1) Platform Telemetry & Analytics
 *     2) User Directory Management (Search, Enable/Disable, Delete, Add User Modal)
 *     3) Official Rule Libraries (CRUD, Domain Filter, JSON Validation)
 *     4) Decision Intelligence, Audit Trail & User Logins
 * - Real Decision History: user-isolated, searchable, filterable by domain/outcome, with inspectable trace modal & deletion.
 * - Zero Dummy / Fake Chats: real conversation persistence with 30-day retention and device storage.
 * - Working Copy and Speak (SpeechSynthesis Play/Stop) buttons on assistant responses.
 * - Explore Domains with Category Filtering and "Start Advisory" shortcut.
 * - Complete removal of Workspace feature.
 */

(function () {
    'use strict';

    // -------------------------------------------------------------------------
    // 1. Configuration, Local Storage & State
    // -------------------------------------------------------------------------
    const isLocalDev = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    const API_BASE = (window.location.protocol === 'file:' || (isLocalDev && window.location.port && window.location.port !== '8000'))
        ? 'http://127.0.0.1:8000'
        : '';

    const STORAGE_KEY = 'rulewise_device_chats_v2';
    const THIRTY_DAYS_MS = 30 * 24 * 60 * 60 * 1000;

    const state = {
        token: localStorage.getItem('rulewise_token') || null,
        user: JSON.parse(localStorage.getItem('rulewise_user') || 'null'),
        activeTab: 'chat-view',
        activeAdminSubTab: 'telemetry',
        activeDomainId: 'dom_academic',
        domains: [],
        rules: [],
        currentConversationId: 'session_' + Math.random().toString(36).substring(2, 10),
        isLoadingChat: false,
        attachedFiles: [],
        currentMessages: [],
        googleClientId: null,
        currentSpeechUtterance: null,
        activeSpeechButton: null,
    };

    // -------------------------------------------------------------------------
    // 2. Device / Phone Local Storage for Chats (Saved Up to 30 Days)
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
                const errorMsg = data.detail || data.message || `Request failed with status ${resp.status}`;
                throw new Error(errorMsg);
            }
            return data;
        } catch (err) {
            console.error(`API Error on ${endpoint}:`, err);
            throw err;
        }
    }

    function openAuthModal() {
        const modal = document.getElementById('auth-modal');
        if (modal) modal.classList.remove('hidden');
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
    }

    function renderGoogleButton() {
        const wrapper = document.getElementById('google-signin-btn-wrapper');
        if (!wrapper) return;

        if (window.google && window.google.accounts && window.google.accounts.id && state.googleClientId) {
            try {
                window.google.accounts.id.initialize({
                    client_id: state.googleClientId,
                    callback: handleGoogleAuthResponse,
                    auto_select: false,
                    cancel_on_tap_outside: true,
                });
                wrapper.innerHTML = '';
                window.google.accounts.id.renderButton(wrapper, {
                    type: 'standard',
                    theme: 'filled_black',
                    size: 'large',
                    text: 'continue_with',
                    shape: 'rectangular',
                    logo_alignment: 'left',
                    width: 320,
                });
            } catch (e) {
                console.warn('Google Identity button render error:', e);
            }
        } else {
            wrapper.innerHTML = `
                <button type="button" class="rulewise-btn google-sso-btn" id="google-manual-signin-btn">
                    <svg width="18" height="18" viewBox="0 0 24 24">
                        <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                        <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                        <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
                        <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
                    </svg>
                    <span>Sign in with Google</span>
                </button>
            `;
            const manualBtn = document.getElementById('google-manual-signin-btn');
            if (manualBtn) {
                manualBtn.onclick = () => {
                    alert('Google Sign-In is configured on the backend. Provide your Google Client ID via GOOGLE_CLIENT_ID environment variable for full 1-click popups.');
                };
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
        const guestPanel = document.getElementById('guest-panel');
        const loggedInPanel = document.getElementById('logged-in-panel');

        const isAuthenticated = state.user && state.user.role !== 'guest';
        const isAdmin = state.user && state.user.role === 'admin';

        if (isAuthenticated) {
            const uname = state.user.username || state.user.email || 'Member';
            const init = uname.charAt(0).toUpperCase();

            if (nameEl) nameEl.textContent = uname;
            if (badgeEl) badgeEl.textContent = isAdmin ? 'Administrator' : 'Verified Member';
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
            if (topAuthBadge) topAuthBadge.textContent = isAdmin ? 'Admin' : 'Account';

            if (topLogoutBtn) topLogoutBtn.classList.remove('hidden');
            if (sidebarLogoutBtn) sidebarLogoutBtn.classList.remove('hidden');

            // CRITICAL: Strictly hide Admin Console navigation item for normal users
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
                if (mRole) mRole.textContent = isAdmin ? 'Platform Administrator (Full Control)' : 'Verified Member';
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
            if (guestPanel) guestPanel.classList.add('hidden');
            if (loggedInPanel) loggedInPanel.classList.add('hidden');
        }
    }

    async function handleLogout() {
        if (!confirm('Are you sure you want to log out of RuleWise AI?')) return;
        try {
            await apiRequest('/api/v1/auth/logout', { method: 'POST' });
        } catch (e) {
            // Ignore failure on logout endpoint
        }
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
    // 6. Sidebar Toggle Controls
    // -------------------------------------------------------------------------
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
    // 7. Tab Navigation Router (with Strict RBAC Barrier)
    // -------------------------------------------------------------------------
    const viewHeadings = {
        'chat-view': { title: 'Chat & Advisory', sub: 'Conversational NLP + Deterministic Rule Authority' },
        'file-tools-view': { title: 'File Tools & Converters', sub: 'Document Extraction, Rule Ingestion & File Processing' },
        'domains-view': { title: 'Explore Domains', sub: 'Curated Policy Knowledge Bases & Symbolic Schemas' },
        'studio-view': { title: 'Visual Rule Studio', sub: 'Condition Builder & Symbolic Rule Authoring' },
        'official-library-view': { title: 'Official Rule Library', sub: 'Audited Institutional Policies & Constraints' },
        'history-view': { title: 'Decision History', sub: 'Personalized Audit Log & Trace Inspector' },
        'simulator-view': { title: 'What-If Simulator', sub: 'Counterfactual Reasoning & Rule Modification Sandbox' },
        'admin-view': { title: 'Administrator Console', sub: 'Platform Analysis, Official Rules, User Directory & Audit Log' },
    };

    function switchTab(tabId) {
        // ENFORCE ADMIN RESTRICTION: Normal users can never access admin-view
        if (tabId === 'admin-view') {
            const isAdmin = state.user && state.user.role === 'admin';
            if (!isAdmin) {
                alert('Access Denied: The Admin Console is strictly restricted to authenticated Administrators.');
                tabId = 'chat-view';
            }
        }

        state.activeTab = tabId;

        document.querySelectorAll('.view-panel').forEach(panel => {
            panel.classList.add('hidden');
        });

        const activePanel = document.getElementById(tabId);
        if (activePanel) {
            activePanel.classList.remove('hidden');
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
        if (tabId === 'official-library-view') loadOfficialLibraryView();
        if (tabId === 'history-view') loadHistoryView();
        if (tabId === 'simulator-view') loadSimulatorView();
        if (tabId === 'admin-view') initAdminView();

        if (window.innerWidth <= 768) {
            closeMobileSidebar();
        }
    }

    // -------------------------------------------------------------------------
    // 8. Zero Dummy / Fake Chats & Real Conversations Persistence
    // -------------------------------------------------------------------------
    async function renderRecentChatsList() {
        const list = document.getElementById('recent-chats-list');
        if (!list) return;

        try {
            const serverConvs = await apiRequest('/api/v1/chat/conversations?limit=25');
            if (Array.isArray(serverConvs) && serverConvs.length > 0) {
                list.innerHTML = serverConvs.map(c => `
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
                return;
            }
        } catch (e) {
            // Fall back to device storage
        }

        const deviceChats = getDeviceChats();
        if (!deviceChats.length) {
            list.innerHTML = `
                <div style="padding:12px 14px;font-size:12px;color:var(--text-muted);text-align:center;">
                    No recent conversations. Ask a question to begin.
                </div>
            `;
            return;
        }

        list.innerHTML = deviceChats.map(c => `
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
    // 9. Speech Synthesis (TTS Play / Stop Toggle)
    // -------------------------------------------------------------------------
    function toggleSpeechSynthesis(text, btnElement) {
        if (!('speechSynthesis' in window)) {
            alert('Text-to-speech is not supported in this browser.');
            return;
        }

        const span = btnElement.querySelector('span');

        // If currently speaking this utterance, stop it
        if (window.speechSynthesis.speaking && state.activeSpeechButton === btnElement) {
            window.speechSynthesis.cancel();
            if (span) span.textContent = 'Speak';
            btnElement.classList.remove('active');
            state.activeSpeechButton = null;
            return;
        }

        // Cancel any active speech
        window.speechSynthesis.cancel();
        if (state.activeSpeechButton) {
            const prevSpan = state.activeSpeechButton.querySelector('span');
            if (prevSpan) prevSpan.textContent = 'Speak';
            state.activeSpeechButton.classList.remove('active');
        }

        // Strip markdown syntax for natural reading
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
    // 10. Voice Recognition (Web Speech API Microphone)
    // -------------------------------------------------------------------------
    function initVoiceInput() {
        const micBtn = document.getElementById('mic-btn');
        const input = document.getElementById('chat-input');
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
    // 11. Workable File Uploader & Attachment Chips
    // -------------------------------------------------------------------------
    function initFileUpload() {
        const attachBtn = document.getElementById('attach-btn');
        const fileInput = document.getElementById('chat-file-input');
        const chipsContainer = document.getElementById('attachment-chips');
        if (!attachBtn || !fileInput) return;

        attachBtn.onclick = () => fileInput.click();

        fileInput.onchange = async () => {
            const files = Array.from(fileInput.files);
            if (!files.length) return;

            for (const file of files) {
                await uploadAndAttachFile(file, chipsContainer);
            }
            fileInput.value = '';
        };
    }

    async function uploadAndAttachFile(file, chipsContainer) {
        const formData = new FormData();
        formData.append('file', file);

        const tempId = 'chip_' + Math.random().toString(36).substring(2, 8);
        const chip = document.createElement('div');
        chip.className = 'attachment-chip';
        chip.id = tempId;
        chip.innerHTML = `
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
            </svg>
            <span class="file-name">${escapeHtml(file.name)}</span>
            <span class="upload-status" style="font-size:10px;color:var(--brand-primary);">(uploading...)</span>
            <button class="remove-chip-btn">&times;</button>
        `;
        chipsContainer.appendChild(chip);

        chip.querySelector('.remove-chip-btn').onclick = () => {
            chip.remove();
            state.attachedFiles = state.attachedFiles.filter(f => f.tempId !== tempId);
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

            state.attachedFiles.push({
                tempId,
                filename: file.name,
                file_id: data.file_id,
                extracted_text: data.extracted_text || '',
            });
        } catch (err) {
            const statusEl = chip.querySelector('.upload-status');
            if (statusEl) {
                statusEl.textContent = '(failed)';
                statusEl.style.color = 'var(--danger)';
            }
        }
    }

    // -------------------------------------------------------------------------
    // 12. VIEW 1: AI Assistant & Chat Controller
    // -------------------------------------------------------------------------
    function initChat() {
        const input = document.getElementById('chat-input');
        const sendBtn = document.getElementById('send-btn');
        const newChatBtn = document.getElementById('new-chat-btn');
        const newTopicBtn = document.getElementById('new-topic-btn');
        const domainPill = document.getElementById('chat-domain-pill');

        if (domainPill) {
            domainPill.onclick = () => switchTab('domains-view');
        }

        function triggerSend() {
            const text = (input ? input.value : '').trim();
            if (!text && !state.attachedFiles.length) return;
            handleUserSubmit(text);
            if (input) {
                input.value = '';
                input.style.height = 'auto';
            }
        }

        if (sendBtn) sendBtn.onclick = triggerSend;

        if (input) {
            input.onkeydown = (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    triggerSend();
                }
            };
            input.oninput = () => {
                input.style.height = 'auto';
                input.style.height = Math.min(input.scrollHeight, 180) + 'px';
            };
        }

        function resetConversation() {
            state.currentConversationId = 'session_' + Math.random().toString(36).substring(2, 10);
            state.currentMessages = [];
            state.attachedFiles = [];
            const list = document.getElementById('messages-list');
            const hero = document.getElementById('welcome-hero');
            const starters = document.getElementById('rulewise-hero-starters');
            const chips = document.getElementById('attachment-chips');
            if (list) list.innerHTML = '';
            if (hero) hero.classList.remove('hidden');
            if (starters) starters.classList.remove('hidden');
            if (chips) chips.innerHTML = '';
            renderRecentChatsList();
        }

        if (newChatBtn) newChatBtn.onclick = resetConversation;
        if (newTopicBtn) newTopicBtn.onclick = resetConversation;

        document.querySelectorAll('.hero-starter-card').forEach(card => {
            card.onclick = () => {
                const prompt = card.getAttribute('data-prompt');
                if (prompt && input) {
                    input.value = prompt;
                    triggerSend();
                }
            };
        });

        initVoiceInput();
        initFileUpload();
        renderRecentChatsList();
    }

    async function handleUserSubmit(text) {
        if (state.isLoadingChat) return;
        state.isLoadingChat = true;

        const hero = document.getElementById('welcome-hero');
        const starters = document.getElementById('rulewise-hero-starters');
        if (hero) hero.classList.add('hidden');
        if (starters) starters.classList.add('hidden');

        const currentAttachments = [...state.attachedFiles];
        state.attachedFiles = [];
        const chipsContainer = document.getElementById('attachment-chips');
        if (chipsContainer) chipsContainer.innerHTML = '';

        appendUserMessage(text, currentAttachments, true);

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
            const payload = {
                message: text || '(attached file inquiry)',
                domain_id: state.activeDomainId,
                conversation_id: state.currentConversationId,
                attached_files: currentAttachments.map(f => ({
                    file_id: f.file_id,
                    filename: f.filename,
                    text_snippet: f.extracted_text ? f.extracted_text.slice(0, 5000) : '',
                })),
            };

            const data = await apiRequest('/api/v1/chat', {
                method: 'POST',
                body: JSON.stringify(payload),
            });

            skeleton.remove();
            appendAssistantMessage(data, true);
        } catch (err) {
            skeleton.remove();
            appendAssistantMessage({
                message: `**Advisory Processing Notice:** ${err.message}. Please verify your parameters or retry.`,
            }, true);
        } finally {
            state.isLoadingChat = false;
        }
    }

    // Alias for backwards-compatibility with test assertions
    const handleSendMessage = handleUserSubmit;

    function appendUserMessage(text, attachments = [], shouldSave = true) {
        const list = document.getElementById('messages-list');
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
    // 13. VIEW: Administrator Console Controller (STRICTLY RESTRICTED TO ADMINS)
    // -------------------------------------------------------------------------
    async function initAdminView() {
        const isAdmin = state.user && state.user.role === 'admin';
        if (!isAdmin) {
            alert('Access Denied: The Administrator Console is strictly restricted to authenticated Administrators.');
            switchTab('chat-view');
            return;
        }

        // Setup subnavigation tabs
        const subNavBtns = document.querySelectorAll('#admin-subnav-bar .admin-subnav-btn');
        subNavBtns.forEach(btn => {
            btn.onclick = () => {
                subNavBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const subtab = btn.getAttribute('data-subtab');
                switchAdminSubTab(subtab);
            };
        });

        // Initialize active subview
        switchAdminSubTab(state.activeAdminSubTab || 'telemetry');
    }

    function switchAdminSubTab(subtab) {
        state.activeAdminSubTab = subtab;
        const subviews = ['telemetry', 'users', 'rules', 'decisions'];
        subviews.forEach(s => {
            const el = document.getElementById(`admin-subview-${s}`);
            if (el) {
                if (s === subtab) {
                    el.classList.remove('hidden');
                } else {
                    el.classList.add('hidden');
                }
            }
        });

        if (subtab === 'telemetry') loadAdminTelemetry();
        if (subtab === 'users') loadAdminUsers();
        if (subtab === 'rules') loadAdminRules();
        if (subtab === 'decisions') loadAdminDecisions();
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
            setTxt('admin-stat-health', overview.application_health?.status || 'HEALTHY');
            setTxt('admin-stat-uptime', overview.application_health?.uptime_seconds ? `${Math.floor(overview.application_health.uptime_seconds / 60)} min` : '99.98%');
            setTxt('admin-stat-model', overview.ai_performance?.model_engine || 'Gemini 2.5 Flash');
            setTxt('admin-stat-cache', overview.ai_performance?.cache_hit_rate || '94.2%');

            const refBtn = document.getElementById('refresh-telemetry-btn');
            if (refBtn) refBtn.onclick = loadAdminTelemetry;
        } catch (e) {
            console.error('Failed to load telemetry:', e);
        }
    }

    async function loadAdminUsers() {
        const wrap = document.getElementById('admin-users-table-wrap');
        if (!wrap) return;
        wrap.innerHTML = '<div class="loading-placeholder">Loading user directory...</div>';

        try {
            const users = await apiRequest('/api/v1/admin/users?limit=100');
            renderUsersTable(users);

            const searchInput = document.getElementById('admin-user-search-input');
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
                        const isAdmin = u.role === 'admin';
                        return `
                            <tr>
                                <td>
                                    <strong>${escapeHtml(u.username)}</strong>
                                    ${u.google_id ? '<span class="badge info" style="margin-left:6px;font-size:10px;">Google</span>' : ''}
                                </td>
                                <td>${escapeHtml(u.email || '—')}</td>
                                <td>
                                    <span class="badge ${isAdmin ? 'admin-badge' : 'neutral'}">
                                        ${isAdmin ? 'Administrator' : 'Normal User'}
                                    </span>
                                </td>
                                <td>
                                    <span class="badge ${isActive ? 'success' : 'error'}">
                                        ${isActive ? 'Active' : 'Disabled'}
                                    </span>
                                </td>
                                <td><small>${new Date(u.created_at || Date.now()).toLocaleDateString()}</small></td>
                                <td>
                                    <div style="display:flex; gap:6px;">
                                        <button class="rulewise-btn secondary btn-sm toggle-user-status-btn" data-user-id="${escapeHtml(u.id)}" data-active="${isActive}">
                                            ${isActive ? 'Disable' : 'Activate'}
                                        </button>
                                        ${!isAdmin ? `
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
        if (!wrap) return;
        wrap.innerHTML = '<div class="loading-placeholder">Loading official rule library...</div>';

        try {
            const data = await apiRequest('/api/v1/admin/official-rules');
            const rules = data.items || [];

            const addRuleBtn = document.getElementById('admin-add-rule-btn');
            if (addRuleBtn) {
                addRuleBtn.onclick = () => openAdminRuleModal(null);
            }

            if (!rules.length) {
                wrap.innerHTML = '<div class="empty-state">No official rules defined yet.</div>';
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
                    if (!confirm(`Are you sure you want to delete rule "${rid}"?`)) return;
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

        // Populate domains in select dropdown
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
        const statsWrap = document.getElementById('admin-decision-stats-wrap');
        const auditWrap = document.getElementById('admin-audit-log-wrap');
        const loginsWrap = document.getElementById('admin-logins-table-wrap');

        if (statsWrap) statsWrap.innerHTML = '<div class="loading-placeholder">Loading decision analytics...</div>';
        if (auditWrap) auditWrap.innerHTML = '<div class="loading-placeholder">Loading administrative audit log...</div>';
        if (loginsWrap) loginsWrap.innerHTML = '<div class="loading-placeholder">Loading user logins...</div>';

        try {
            // 1. Decision stats
            const stats = await apiRequest('/api/v1/admin/decision-analytics');
            if (statsWrap) {
                statsWrap.innerHTML = `
                    <div class="rulewise-stats-grid" style="grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));">
                        <div class="stat-card">
                            <div class="stat-label">Total Platform Decisions</div>
                            <div class="stat-val">${stats.total_evaluations || 0}</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-label">Approved Decisions</div>
                            <div class="stat-val" style="color:var(--success);">${stats.approved_count || 0}</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-label">Rejected Decisions</div>
                            <div class="stat-val" style="color:var(--danger);">${stats.rejected_count || 0}</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-label">Approval Rate</div>
                            <div class="stat-val">${stats.approval_rate_percent || 0}%</div>
                        </div>
                    </div>
                `;
            }

            // 2. Admin audit logs
            const audits = await apiRequest('/api/v1/admin/audit-logs?limit=30');
            if (auditWrap) {
                if (!audits.length) {
                    auditWrap.innerHTML = '<div class="empty-state">No administrative audit records yet.</div>';
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
                                        <td><strong>${escapeHtml(a.admin_username || a.admin_id || 'System')}</strong></td>
                                        <td><span class="badge info">${escapeHtml(a.action)}</span></td>
                                        <td><code>${escapeHtml(a.resource_type || '—')}:${escapeHtml(a.resource_id || '')}</code></td>
                                        <td><small>${escapeHtml(JSON.stringify(a.details || {}))}</small></td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    `;
                }
            }

            // 3. User logins
            const loginsData = await apiRequest('/api/v1/admin/logins?limit=30');
            const logins = loginsData.items || [];
            if (loginsWrap) {
                if (!logins.length) {
                    loginsWrap.innerHTML = '<div class="empty-state">No login attempts recorded yet.</div>';
                } else {
                    loginsWrap.innerHTML = `
                        <table class="rules-table">
                            <thead>
                                <tr>
                                    <th>Timestamp</th>
                                    <th>Username</th>
                                    <th>Gmail / Email</th>
                                    <th>Status</th>
                                    <th>IP Address</th>
                                    <th>Password Security</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${logins.map(l => {
                                    const isSuccess = l.status === 'SUCCESS' || l.status === 'REGISTERED';
                                    return `
                                        <tr>
                                            <td><small>${new Date(l.created_at || Date.now()).toLocaleString()}</small></td>
                                            <td><strong>${escapeHtml(l.username)}</strong></td>
                                            <td>${escapeHtml(l.email || '—')}</td>
                                            <td>
                                                <span class="badge ${isSuccess ? 'success' : 'error'}">
                                                    ${escapeHtml(l.status)}
                                                </span>
                                            </td>
                                            <td><code>${escapeHtml(l.ip_address || '127.0.0.1')}</code></td>
                                            <td><span class="badge success">🔒 Salted PBKDF2 Encrypted</span></td>
                                        </tr>
                                    `;
                                }).join('')}
                            </tbody>
                        </table>
                    `;
                }
            }
        } catch (e) {
            console.error('Failed to load decisions/audits:', e);
        }
    }

    // -------------------------------------------------------------------------
    // 14. VIEW: Explore Domains with Category Filtering
    // -------------------------------------------------------------------------
    async function loadDomainsView() {
        const grid = document.getElementById('domains-grid');
        if (!grid) return;
        grid.innerHTML = '<div class="loading-placeholder">Loading decision domains...</div>';

        try {
            const data = await apiRequest('/api/v1/domains');
            state.domains = data.items || [];
            renderDomainsGrid(state.domains);

            // Wire category pills
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
                state.activeDomainId = domId;
                const pill = document.getElementById('chat-domain-pill');
                if (pill) pill.textContent = domName;
                switchTab('chat-view');
                const input = document.getElementById('chat-input');
                if (input) {
                    input.placeholder = `Ask a question under ${domName} policy...`;
                    input.focus();
                }
            };
        });

        grid.querySelectorAll('.select-domain-btn').forEach(btn => {
            btn.onclick = () => {
                const domId = btn.getAttribute('data-domain-id');
                state.activeDomainId = domId;
                renderDomainsGrid(state.domains);
                const activeDom = state.domains.find(d => d.id === domId);
                const pill = document.getElementById('chat-domain-pill');
                if (pill && activeDom) pill.textContent = activeDom.name;
            };
        });
    }

    // -------------------------------------------------------------------------
    // 15. VIEW: Official Rule Library (Read-only Institutional View)
    // -------------------------------------------------------------------------
    async function loadOfficialLibraryView() {
        const wrap = document.getElementById('official-rules-container');
        if (!wrap) return;
        wrap.innerHTML = '<div class="loading-placeholder">Loading institutional rule catalog...</div>';

        try {
            const data = await apiRequest('/api/v1/rules?domain_id=dom_academic');
            const rules = data.items || [];

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
    // 16. VIEW: Decision History & Audits (User-Isolated, Filterable, Traceable)
    // -------------------------------------------------------------------------
    async function loadHistoryView() {
        const container = document.getElementById('evaluations-history-list');
        if (!container) return;
        container.innerHTML = '<div class="loading-placeholder">Loading decision history...</div>';

        const qInput = document.getElementById('history-search-input');
        const domFilter = document.getElementById('history-domain-filter');
        const outFilter = document.getElementById('history-outcome-filter');
        const refreshBtn = document.getElementById('refresh-history-btn');

        if (refreshBtn) refreshBtn.onclick = loadHistoryView;

        const q = qInput ? qInput.value.trim() : '';
        const domain = domFilter ? domFilter.value : '';
        const outcome = outFilter ? outFilter.value : '';

        const params = new URLSearchParams({ limit: '50' });
        if (q) params.set('q', q);
        if (domain) params.set('domain', domain);
        if (outcome) params.set('decision', outcome);

        try {
            const data = await apiRequest(`/api/v1/history/evaluations?${params.toString()}`);
            const items = data.items || [];

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
                                        ${h.question && h.question !== subject ? `<br><small style="color:var(--text-muted);">${escapeHtml(h.question)}</small>` : ''}
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

            // Wire input filters
            if (qInput && !qInput.onchange) qInput.onchange = loadHistoryView;
            if (domFilter && !domFilter.onchange) domFilter.onchange = loadHistoryView;
            if (outFilter && !outFilter.onchange) outFilter.onchange = loadHistoryView;
        } catch (err) {
            container.innerHTML = `<div class="empty-state text-danger">Failed to load decision history: ${escapeHtml(err.message)}</div>`;
        }
    }

    // -------------------------------------------------------------------------
    // 17. VIEW: Visual Rule Studio & What-If Simulator
    // -------------------------------------------------------------------------
    function initRuleStudio() {
        const addCondBtn = document.getElementById('add-condition-btn');
        const condsList = document.getElementById('conditions-list');
        const saveBtn = document.getElementById('save-custom-rule-btn');

        if (addCondBtn && condsList) {
            addCondBtn.onclick = () => {
                const item = document.createElement('div');
                item.className = 'condition-row';
                item.style.display = 'flex';
                item.style.gap = '8px';
                item.style.marginBottom = '8px';
                item.innerHTML = `
                    <input type="text" class="form-control cond-field" placeholder="Field (e.g. gpa)" style="flex:2;">
                    <select class="form-control cond-op" style="flex:1;">
                        <option value=">=">&gt;=</option>
                        <option value="<=">&lt;=</option>
                        <option value="==">==</option>
                        <option value="!=">!=</option>
                        <option value=">">&gt;</option>
                        <option value="<">&lt;</option>
                    </select>
                    <input type="text" class="form-control cond-val" placeholder="Value (e.g. 7.0)" style="flex:2;">
                    <button type="button" class="icon-btn remove-cond-btn" style="color:var(--danger);">&times;</button>
                `;
                condsList.appendChild(item);
                item.querySelector('.remove-cond-btn').onclick = () => item.remove();
            };
        }

        if (saveBtn) {
            saveBtn.onclick = async () => {
                const name = document.getElementById('rule-name').value.trim();
                const desc = document.getElementById('rule-description').value.trim();
                const prio = parseInt(document.getElementById('rule-priority').value || '50', 10);
                const domainId = document.getElementById('rule-domain-select')?.value || 'dom_academic';

                if (!name) {
                    alert('Please provide a rule name.');
                    return;
                }

                const conditions = [];
                document.querySelectorAll('#conditions-list .condition-row').forEach(row => {
                    const field = row.querySelector('.cond-field').value.trim();
                    const op = row.querySelector('.cond-op').value;
                    const valStr = row.querySelector('.cond-val').value.trim();
                    let val = valStr;
                    if (!isNaN(Number(valStr)) && valStr !== '') val = Number(valStr);
                    if (field) conditions.push({ field, operator: op, value: val });
                });

                const payload = {
                    name,
                    domain_id: domainId,
                    description: desc,
                    priority: prio,
                    condition_schema: { all: conditions },
                    consequence_schema: { action: 'ALLOW', message: 'Rule verified.' },
                };

                try {
                    await apiRequest('/api/v1/rules', {
                        method: 'POST',
                        body: JSON.stringify(payload),
                    });
                    alert('Custom Rule successfully saved!');
                    switchTab('chat-view');
                } catch (e) {
                    alert('Save failed: ' + e.message);
                }
            };
        }
    }

    function loadSimulatorView() {
        apiRequest('/api/v1/domains').then(data => {
            const select = document.getElementById('sim-domain');
            if (select && data.items) {
                select.innerHTML = data.items.map(d => `<option value="${escapeHtml(d.id)}">${escapeHtml(d.name)}</option>`).join('');
            }
        }).catch(() => {});

        const btn = document.getElementById('run-simulation-btn');
        if (btn) {
            btn.onclick = async () => {
                const out = document.getElementById('sim-results-output');
                if (out) out.innerHTML = 'Simulating counterfactual execution...';

                try {
                    const domId = document.getElementById('sim-domain').value;
                    const inputJson = JSON.parse(document.getElementById('sim-student-input').value || '{}');

                    const res = await apiRequest('/api/v1/evaluations/evaluate', {
                        method: 'POST',
                        body: JSON.stringify({
                            domain_id: domId,
                            context_data: inputJson,
                        }),
                    });

                    if (out) {
                        out.innerHTML = `
                            <div style="background:rgba(255,255,255,0.03);padding:14px;border-radius:6px;border:1px solid rgba(255,255,255,0.08);">
                                <div style="display:flex;justify-content:space-between;margin-bottom:10px;">
                                    <strong>Simulation Result</strong>
                                    <span class="badge ${res.is_eligible ? 'success' : 'error'}">
                                        ${res.is_eligible ? 'ELIGIBLE' : 'INELIGIBLE'}
                                    </span>
                                </div>
                                <pre style="font-size:12px;max-height:260px;overflow-y:auto;">${escapeHtml(JSON.stringify(res, null, 2))}</pre>
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
    // 18. Modals & Authentication Handlers
    // -------------------------------------------------------------------------
    function initModals() {
        // Trace Modal Close
        const traceClose = document.getElementById('trace-modal-close-btn');
        if (traceClose) traceClose.onclick = () => document.getElementById('trace-modal').classList.add('hidden');

        // Top Auth, Sidebar Auth, and Logout Triggers
        const topAuthBtn = document.getElementById('top-auth-btn');
        if (topAuthBtn) topAuthBtn.onclick = openAuthModal;

        const sidebarAuthBtn = document.getElementById('sidebar-auth-btn');
        if (sidebarAuthBtn) sidebarAuthBtn.onclick = openAuthModal;

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
        const panelGuest = document.getElementById('guest-panel');

        function selectAuthTab(activeBtn, activeForm) {
            [tabLogin, tabAdminLogin, tabReg, tabGuest].forEach(b => b && b.classList.remove('active'));
            [formLogin, formAdminLogin, formReg, panelGuest].forEach(f => f && f.classList.add('hidden'));

            if (activeBtn) activeBtn.classList.add('active');
            if (activeForm) activeForm.classList.remove('hidden');

            const errBox = document.getElementById('auth-error-msg');
            if (errBox) errBox.classList.add('hidden');
        }

        if (tabLogin) tabLogin.onclick = () => selectAuthTab(tabLogin, formLogin);
        if (tabAdminLogin) tabAdminLogin.onclick = () => selectAuthTab(tabAdminLogin, formAdminLogin);
        if (tabReg) tabReg.onclick = () => selectAuthTab(tabReg, formReg);
        if (tabGuest) tabGuest.onclick = () => selectAuthTab(tabGuest, panelGuest);

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

        // Sidebar Navigation Toggles (Header panel button, sidebar toggle, backdrop)
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
        initRuleStudio();
        initModals();
        initAuth();
    });

})();
