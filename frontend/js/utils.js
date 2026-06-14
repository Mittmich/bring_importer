function showBringWidget(recipeUuid) {
  // Get the elements we need to update
  const bringImportCard = document.getElementById('bringImportCard');

  // Set the recipe URL for the Bring widget
  const recipeUrl = `${config.frontendUrl}/api/recipes/${recipeUuid}.html`;
  bringImportCard.setAttribute('data-bring-import', recipeUrl);
  console.log('Setting Bring widget import URL:', recipeUrl);
  window.bringwidgets.import.setUrl(recipeUrl);

  // Show the card
  bringImportCard.style.display = 'block';
  bringImportCard.classList.remove('d-none');

  // Force widget to reload with new data
  if (window.bringUpdateWidgets) {
    window.bringUpdateWidgets();
  } else {
    // Fallback: reload the Bring widget script
    const oldScript = document.querySelector('script[src*="platform.getbring.com"]');
    if (oldScript) {
      oldScript.remove();
    }

    const newScript = document.createElement('script');
    newScript.async = true;
    newScript.src = 'https://platform.getbring.com/widgets/import.js';
    document.head.appendChild(newScript);
  }
}
