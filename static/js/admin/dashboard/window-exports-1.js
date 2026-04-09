// Make functions globally available
window.switchTab = switchTab;
window.openAdminSidebar = openAdminSidebar;
window.closeAdminSidebar = closeAdminSidebar;
window.exportData = exportData;
window.refreshDashboard = refreshDashboard;
window.openSettings = openSettings;
window.openEmailTemplates = openEmailTemplates;
window.emailTemplatePrev = emailTemplatePrev;
window.emailTemplateNext = emailTemplateNext;
window.closeEmailTemplatesModal = closeEmailTemplatesModal;
window.openSecuritySettings = openSecuritySettings;
window.openFeeConfig = openFeeConfig;
window.closeFeeConfigModal = closeFeeConfigModal;
window.saveFeeConfig = saveFeeConfig;
window.openApiManagement = openApiManagement;
window.viewUser = viewUser;
window.messageUser = messageUser;
window.sendAdminMessage = sendAdminMessage;
window.closeMessageModal = closeMessageModal;
window.freezeUser = freezeUser;
window.deleteUser = deleteUser;
window.resetBidStrikes = resetBidStrikes;
window.toggleSelectAll = toggleSelectAll;
window.updateBulkActionBar = updateBulkActionBar;
window.clearBulkSelection = clearBulkSelection;
window.bulkFreezeUsers = bulkFreezeUsers;
window.bulkDeleteUsers = bulkDeleteUsers;
window.viewOrder = viewOrder;
window.closeUserModal = closeUserModal;
window.closeOrderModal = closeOrderModal;
window.closeConfirmModal = closeConfirmModal;
window.confirmAction = confirmAction;
window.showConfirmSuccess = showConfirmSuccess;
window.closeConfirmModalAndRefresh = closeConfirmModalAndRefresh;
window.openClearDataModal = openClearDataModal;
window.closeClearDataModal = closeClearDataModal;
window.closeClearDataModalAndRefresh = closeClearDataModalAndRefresh;
window.showClearDataSuccess = showClearDataSuccess;
window.executeClearData = executeClearData;
window.selectAllClearOptions = selectAllClearOptions;
window.deselectAllClearOptions = deselectAllClearOptions;
window.selectMarketplaceData = selectMarketplaceData;
window.validateClearDataForm = validateClearDataForm;
window.updateSelectedCount = updateSelectedCount;

// ============================================
// DISPUTES / REPORTS FUNCTIONS
// ============================================

let disputesData = [];
let currentReportId = null;

