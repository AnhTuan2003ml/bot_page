// Bot Admin Panel JavaScript

// Utility Functions
function showAlert(message, type = 'success') {
    const container = document.getElementById('alert-container');
    if (!container) return;
    
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.textContent = message;
    container.appendChild(alert);
    setTimeout(() => alert.remove(), 5000);
}

function formatPrice(price) {
    return price ? price.toLocaleString() + ' VNĐ' : 'Liên hệ';
}

function formatDate(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleDateString('vi-VN');
}

// Status translation to Vietnamese
function getStatusLabel(status) {
    const labels = {
        'available': 'Hoạt động',
        'sold': 'Đã xử lý',
        'reserved': 'Chờ xử lý'
    };
    return labels[status] || status;
}

// Message Stats API
async function loadMessageStats() {
    try {
        const res = await fetch('/api/message-stats');
        const data = await res.json();
        
        const tbody = document.getElementById('message-stats-table');
        if (!tbody) return;
        
        if (data.success && data.stats.length > 0) {
            tbody.innerHTML = data.stats.map(s => `
                <tr>
                    <td><code>${s.page_id}</code></td>
                    <td><strong>${s.total_messages.toLocaleString()}</strong></td>
                    <td>${s.unique_senders.toLocaleString()}</td>
                    <td>
                        <button class="btn btn-sm btn-primary" onclick="viewPageMessageStats('${s.page_id}')">
                            📊 Chi tiết
                        </button>
                    </td>
                </tr>
            `).join('');
        } else {
            tbody.innerHTML = '<tr><td colspan="4" class="empty-state">Chưa có dữ liệu tin nhắn</td></tr>';
        }
    } catch (e) {
        console.error('Load message stats error:', e);
    }
}

async function viewPageMessageStats(pageId) {
    try {
        const res = await fetch(`/api/pages/${pageId}/message-stats`);
        const data = await res.json();
        
        const contentDiv = document.getElementById('message-stats-content');
        if (data.success) {
            const stats = data.stats;
            contentDiv.innerHTML = `
                <div style="margin-bottom: 16px;">
                    <h4 style="margin: 0 0 8px 0;">Page: ${stats.page_id}</h4>
                    <p style="margin: 0; color: var(--gray-500);">
                        <strong>${stats.total_messages.toLocaleString()}</strong> tin nhắn từ 
                        <strong>${stats.unique_senders.toLocaleString()}</strong> người
                    </p>
                </div>
                <div class="table-container" style="max-height: 400px;">
                    <table>
                        <thead>
                            <tr>
                                <th>Người dùng</th>
                                <th>Số tin</th>
                                <th>Lần đầu</th>
                                <th>Lần cuối</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${stats.senders.map(s => `
                                <tr>
                                    <td>
                                        <strong>${s.sender_name}</strong><br>
                                        <small style="color: var(--gray-500);">${s.sender_psid}</small>
                                    </td>
                                    <td><strong>${s.message_count.toLocaleString()}</strong></td>
                                    <td>${formatDate(s.first_message_at)}</td>
                                    <td>${formatDate(s.last_message_at)}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            `;
        } else {
            contentDiv.innerHTML = '<p class="text-error">Không thể tải dữ liệu</p>';
        }
        
        document.getElementById('message-stats-modal').classList.remove('hidden');
    } catch (e) {
        console.error('View message stats error:', e);
    }
}

function closeMessageStatsModal() {
    document.getElementById('message-stats-modal').classList.add('hidden');
}

// Stats API
async function loadStats() {
    try {
        const res = await fetch('/api/stats');
        const data = await res.json();
        if (data.success) {
            const totalEl = document.getElementById('stat-total');
            const availableEl = document.getElementById('stat-available');
            const soldEl = document.getElementById('stat-sold');
            const reservedEl = document.getElementById('stat-reserved');
            
            if (totalEl) totalEl.textContent = data.data.total;
            if (availableEl) availableEl.textContent = data.data.available;
            if (soldEl) soldEl.textContent = data.data.sold;
            if (reservedEl) reservedEl.textContent = data.data.reserved;
        }
    } catch (e) {
        console.error('Load stats error:', e);
    }
}

// Plates API
async function loadPlates() {
    try {
        const res = await fetch('/api/plates');
        const data = await res.json();
        const tbody = document.getElementById('plates-table');
        
        if (!tbody) return;
        
        if (data.success && data.data.length > 0) {
            tbody.innerHTML = data.data.map(p => `
                <tr>
                    <td>${p.id}</td>
                    <td><strong>${p.plate_number}</strong></td>
                    <td>${formatPrice(p.price)}</td>
                    <td>${p.vehicle_type || '-'}</td>
                    <td><span class="badge badge-${p.status}">${getStatusLabel(p.status)}</span></td>
                    <td>${formatDate(p.updated_at)}</td>
                    <td>
                        <div class="action-btns">
                            <button class="btn btn-primary" onclick="openEditModal('${p.plate_number}', ${p.price || 0}, '${p.status}', '${p.vehicle_type || ''}')">Sửa</button>
                            <button class="btn btn-danger" onclick="deletePlate('${p.plate_number}')">Xóa</button>
                        </div>
                    </td>
                </tr>
            `).join('');
        } else {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">Chưa có biển số nào</td></tr>';
        }
    } catch (e) {
        console.error('Load plates error:', e);
        const tbody = document.getElementById('plates-table');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="8" class="empty-state">Lỗi tải dữ liệu</td></tr>';
        }
    }
}

async function addPlate() {
    const number = document.getElementById('new-plate-number')?.value;
    const price = document.getElementById('new-plate-price')?.value;
    const status = document.getElementById('new-plate-status')?.value;

    if (!number) {
        showAlert('Vui lòng nhập biển số!', 'error');
        return;
    }

    try {
        const res = await fetch('/api/plates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ plate_number: number, price: parseInt(price) || 0, status })
        });
        const data = await res.json();
        
        if (data.success) {
            showAlert('Đã thêm biển số!');
            document.getElementById('new-plate-number').value = '';
            document.getElementById('new-plate-price').value = '';
            loadPlates();
            loadStats();
        } else {
            showAlert(data.error || 'Lỗi!', 'error');
        }
    } catch (e) {
        showAlert('Lỗi kết nối!', 'error');
    }
}

async function deletePlate(plateNumber) {
    try {
        const res = await fetch(`/api/plates/${plateNumber}`, { method: 'DELETE' });
        const data = await res.json();
        
        if (data.success) {
            showAlert('Đã xóa!');
            loadPlates();
            loadStats();
        } else {
            showAlert(data.error || 'Lỗi!', 'error');
        }
    } catch (e) {
        showAlert('Lỗi kết nối!', 'error');
    }
}

// Edit Modal Functions
let currentEditPlate = null;

function openEditModal(plateNumber, currentPrice, currentStatus, vehicleType = "") {
    currentEditPlate = plateNumber;
    const modal = document.getElementById('edit-modal');
    const plateNumberEl = document.getElementById('edit-plate-number');
    if (plateNumberEl) plateNumberEl.textContent = plateNumber;
    const editPrice = document.getElementById('edit-price');
    if (editPrice) editPrice.value = currentPrice || 0;
    const editStatus = document.getElementById('edit-status');
    if (editStatus) editStatus.value = currentStatus;
    const editVehicle = document.getElementById('edit-vehicle-type');
    if (editVehicle) editVehicle.value = vehicleType || '';
    if (modal) modal.classList.remove('hidden');
}

function closeEditModal() {
    const modal = document.getElementById('edit-modal');
    if (modal) modal.classList.add('hidden');
    currentEditPlate = null;
}

async function savePlateEdit() {
    if (!currentEditPlate) return;
    
    const price = document.getElementById('edit-price').value;
    const status = document.getElementById('edit-status').value;

    try {
        const res = await fetch(`/api/plates/${currentEditPlate}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ price: parseInt(price) || 0, status })
        });
        const data = await res.json();
        
        if (data.success) {
            showAlert('Đã cập nhật!');
            closeEditModal();
            loadPlates();
            loadStats();
        } else {
            showAlert(data.error || 'Lỗi!', 'error');
        }
    } catch (e) {
        showAlert('Lỗi kết nối!', 'error');
    }
}

// AI Service Functions
async function setSkill() {
    const skill = document.getElementById('ai-skill')?.value;
    if (!skill) return;
    
    try {
        const res = await fetch('/api/ai/skill', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ skill })
        });
        const data = await res.json();
        
        if (data.success) {
            showAlert(`Đã đổi skill thành: ${skill}`);
            const currentSkillEl = document.getElementById('current-skill');
            if (currentSkillEl) currentSkillEl.textContent = skill;
        } else {
            showAlert(data.error || 'Lỗi!', 'error');
        }
    } catch (e) {
        showAlert('Lỗi kết nối!', 'error');
    }
}

async function setProvider() {
    const provider = document.getElementById('ai-provider')?.value;
    if (!provider) return;
    
    try {
        const res = await fetch('/api/ai/provider', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider })
        });
        const data = await res.json();
        
        if (data.success) {
            showAlert(`Đã đổi provider thành: ${provider}`);
            const currentProviderEl = document.getElementById('current-provider');
            if (currentProviderEl) currentProviderEl.textContent = provider;
        } else {
            showAlert(data.error || 'Lỗi!', 'error');
        }
    } catch (e) {
        showAlert('Lỗi kết nối!', 'error');
    }
}

async function testAI() {
    const message = document.getElementById('test-message')?.value;
    if (!message) {
        showAlert('Vui lòng nhập tin nhắn!', 'error');
        return;
    }

    const responseDiv = document.getElementById('test-response');
    if (!responseDiv) return;
    
    responseDiv.textContent = 'Đang chờ phản hồi...';
    responseDiv.classList.remove('hidden');

    try {
        const res = await fetch('/api/ai/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message })
        });
        const data = await res.json();
        
        if (data.success) {
            responseDiv.textContent = `🤖 AI: ${data.response}`;
        } else {
            responseDiv.textContent = `❌ Lỗi: ${data.error}`;
        }
    } catch (e) {
        responseDiv.textContent = '❌ Lỗi kết nối!';
    }
}

// Skill Editor Functions
async function loadSkillContent() {
    const skillName = document.getElementById('edit-skill-select')?.value;
    if (!skillName) {
        document.getElementById('skill-content').value = '';
        return;
    }
    
    try {
        const res = await fetch(`/api/skills/${skillName}`);
        const data = await res.json();
        
        if (data.success) {
            document.getElementById('skill-content').value = data.content;
            updateSkillStatus('✅ Đã load skill content', 'success');
        } else {
            updateSkillStatus('❌ Không thể load skill', 'error');
        }
    } catch (e) {
        updateSkillStatus('❌ Lỗi kết nối!', 'error');
    }
}

async function saveSkillContent() {
    const skillName = document.getElementById('edit-skill-select')?.value;
    const content = document.getElementById('skill-content')?.value;
    
    if (!skillName) {
        updateSkillStatus('⚠️ Vui lòng chọn skill!', 'error');
        return;
    }
    if (!content.trim()) {
        updateSkillStatus('⚠️ Content không được để trống!', 'error');
        return;
    }
    
    try {
        const res = await fetch(`/api/skills/${skillName}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content })
        });
        const data = await res.json();
        
        if (data.success) {
            updateSkillStatus('✅ Đã lưu skill thành công!', 'success');
            showAlert('Skill đã được cập nhật!');
        } else {
            updateSkillStatus(`❌ Lỗi: ${data.error}`, 'error');
        }
    } catch (e) {
        updateSkillStatus('❌ Lỗi kết nối!', 'error');
    }
}

async function createNewSkill() {
    const name = prompt('Nhập tên skill mới (ví dụ: custom_sales):');
    if (!name) return;
    
    const content = document.getElementById('skill-content')?.value;
    if (!content.trim()) {
        alert('Vui lòng nhập nội dung skill trước!');
        return;
    }
    
    try {
        const res = await fetch('/api/skills', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, content })
        });
        const data = await res.json();
        
        if (data.success) {
            // Add to select
            const select = document.getElementById('edit-skill-select');
            const option = new Option(name, name);
            select.add(option);
            select.value = name;
            updateSkillStatus('✅ Đã tạo skill mới!', 'success');
            showAlert('Skill mới đã được tạo!');
        } else {
            updateSkillStatus(`❌ Lỗi: ${data.error}`, 'error');
        }
    } catch (e) {
        updateSkillStatus('❌ Lỗi kết nối!', 'error');
    }
}

async function deleteSkill() {
    const skillName = document.getElementById('edit-skill-select')?.value;
    if (!skillName) {
        updateSkillStatus('⚠️ Vui lòng chọn skill!', 'error');
        return;
    }
    
    try {
        const res = await fetch(`/api/skills/${skillName}`, {
            method: 'DELETE'
        });
        const data = await res.json();
        
        if (data.success) {
            // Remove from select
            const select = document.getElementById('edit-skill-select');
            select.remove(select.selectedIndex);
            select.value = '';
            document.getElementById('skill-content').value = '';
            updateSkillStatus('✅ Đã xóa skill!', 'success');
            showAlert('Skill đã bị xóa!');
        } else {
            updateSkillStatus(`❌ Lỗi: ${data.error}`, 'error');
        }
    } catch (e) {
        updateSkillStatus('❌ Lỗi kết nối!', 'error');
    }
}

function updateSkillStatus(message, type) {
    const statusEl = document.getElementById('skill-save-status');
    if (statusEl) {
        statusEl.textContent = message;
        statusEl.style.color = type === 'error' ? '#dc3545' : '#28a745';
    }
}

// Page Config Functions - Separate update functions

// Update App ID only
async function updateAppId() {
    const appId = document.getElementById('fb-app-id')?.value;
    if (!appId) {
        showAlert('Vui lòng nhập App ID!', 'error');
        return;
    }

    try {
        const res = await fetch('/api/config/app-id', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ app_id: appId })
        });
        const data = await res.json();

        if (data.success) {
            showAlert('✅ Đã cập nhật App ID!');
            document.getElementById('fb-app-id').value = '';
            setTimeout(() => location.reload(), 1000);
        } else {
            showAlert(data.error || 'Lỗi!', 'error');
        }
    } catch (e) {
        showAlert('Lỗi kết nối!', 'error');
    }
}

// Update App Secret only
async function updateAppSecret() {
    const appSecret = document.getElementById('fb-app-secret')?.value;
    if (!appSecret) {
        showAlert('Vui lòng nhập App Secret!', 'error');
        return;
    }

    try {
        const res = await fetch('/api/config/app-secret', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ app_secret: appSecret })
        });
        const data = await res.json();

        if (data.success) {
            showAlert('✅ Đã cập nhật App Secret!');
            document.getElementById('fb-app-secret').value = '';
            setTimeout(() => location.reload(), 1000);
        } else {
            showAlert(data.error || 'Lỗi!', 'error');
        }
    } catch (e) {
        showAlert('Lỗi kết nối!', 'error');
    }
}

// Exchange token flow
async function exchangeAndSaveToken() {
    const token = document.getElementById('fb-token')?.value;

    if (!token) {
        showAlert('Vui lòng nhập User Access Token!', 'error');
        return;
    }

    try {
        const res = await fetch('/api/config/token', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: token })
        });
        const data = await res.json();

        if (data.success) {
            const pageInfo = data.page_name ? ` cho page "${data.page_name}"` : '';
            showAlert(`✅ Đã cập nhật${pageInfo}! ${data.message}`);
            document.getElementById('fb-token').value = '';
            setTimeout(() => location.reload(), 2000);
        } else {
            showAlert(data.error || 'Lỗi!', 'error');
        }
    } catch (e) {
        showAlert('Lỗi kết nối!', 'error');
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Load data based on current page
    if (document.getElementById('stat-total')) {
        loadStats();
    }
    if (document.getElementById('plates-table')) {
        loadPlates();
    }
    
    // Close modal on overlay click
    window.onclick = function(event) {
        const addModal = document.getElementById('add-modal');
        const editModal = document.getElementById('edit-modal');
        if (event.target === addModal) {
            if (typeof closeAddModal === 'function') closeAddModal();
            else if (editModal) editModal.classList.add('hidden');
        }
        if (event.target === editModal) {
            if (typeof closeEditModal === 'function') closeEditModal();
            else if (editModal) editModal.classList.add('hidden');
        }
    }
    
    // Load current page from localStorage and set selector
    const currentPageId = localStorage.getItem('current_page_id');
    const pageSelector = document.getElementById('header-page-selector');
    if (pageSelector && currentPageId) {
        pageSelector.value = currentPageId;
    }
});

// ==================== MULTI-PAGE SUPPORT ====================

/**
 * Switch to a different page context
 * @param {string} pageId - The page ID to switch to
 */
function switchPage(pageId) {
    if (!pageId) return;
    
    // Save to localStorage
    localStorage.setItem('current_page_id', pageId);
    
    // Show notification
    showAlert(`Đã chuyển sang page: ${pageId}`);
    
    // Reload page to apply new context (optional - depends on implementation)
    // window.location.reload();
}

/**
 * Get current page ID from localStorage
 * @returns {string|null} Current page ID or null
 */
function getCurrentPageId() {
    return localStorage.getItem('current_page_id');
}

/**
 * Clear current page selection
 */
function clearCurrentPage() {
    localStorage.removeItem('current_page_id');
}
