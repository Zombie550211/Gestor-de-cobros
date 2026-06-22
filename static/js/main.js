function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  sidebar.classList.toggle('open');
}

document.addEventListener('click', (e) => {
  const sidebar = document.getElementById('sidebar');
  const menuBtn = document.querySelector('.menu-btn');
  if (
    sidebar &&
    sidebar.classList.contains('open') &&
    !sidebar.contains(e.target) &&
    (!menuBtn || !menuBtn.contains(e.target))
  ) {
    sidebar.classList.remove('open');
  }
});
