// Paste this in your browser console AFTER opening the success modal
// This will show you exactly what's wrong

console.log('========================================');
console.log('🔍 DEBUGGING MODAL PRICING DISPLAY');
console.log('========================================');

// Check if rows exist
const currentSpotRow = document.getElementById('success-current-spot-row');
const premiumRow = document.getElementById('success-premium-row');
const floorRow = document.getElementById('success-floor-row');
const effectiveRow = document.getElementById('success-effective-row');

console.log('\n📋 Element Check:');
console.log('currentSpotRow exists:', !!currentSpotRow);
console.log('premiumRow exists:', !!premiumRow);
console.log('floorRow exists:', !!floorRow);
console.log('effectiveRow exists:', !!effectiveRow);

if (currentSpotRow) {
    console.log('\n🎯 Current Spot Row:');
    console.log('  inline style.display:', currentSpotRow.style.display);
    console.log('  computed display:', window.getComputedStyle(currentSpotRow).display);
    console.log('  offsetHeight:', currentSpotRow.offsetHeight);
    console.log('  visible:', currentSpotRow.offsetHeight > 0);
}

if (premiumRow) {
    console.log('\n💰 Premium Row:');
    console.log('  inline style.display:', premiumRow.style.display);
    console.log('  computed display:', window.getComputedStyle(premiumRow).display);
    console.log('  offsetHeight:', premiumRow.offsetHeight);
    console.log('  visible:', premiumRow.offsetHeight > 0);
    console.log('  text content:', document.getElementById('success-premium')?.textContent);
}

if (floorRow) {
    console.log('\n📊 Floor Row:');
    console.log('  inline style.display:', floorRow.style.display);
    console.log('  computed display:', window.getComputedStyle(floorRow).display);
    console.log('  offsetHeight:', floorRow.offsetHeight);
    console.log('  visible:', floorRow.offsetHeight > 0);
    console.log('  text content:', document.getElementById('success-floor')?.textContent);
}

if (effectiveRow) {
    console.log('\n✨ Effective Row:');
    console.log('  inline style.display:', effectiveRow.style.display);
    console.log('  computed display:', window.getComputedStyle(effectiveRow).display);
    console.log('  offsetHeight:', effectiveRow.offsetHeight);
    console.log('  visible:', effectiveRow.offsetHeight > 0);
    console.log('  text content:', document.getElementById('success-effective')?.textContent);
}

console.log('\n========================================');
