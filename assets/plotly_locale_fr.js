/* Traduction française de la barre d'outils Plotly (chargée de façon asynchrone par Dash). */
(function register() {
  if (!window.Plotly || !window.Plotly.register) { return setTimeout(register, 150); }
  window.Plotly.register({
    moduleType: "locale", name: "fr",
    dictionary: {
      "Download plot as a png": "Télécharger en PNG", "Download plot": "Télécharger le graphique",
      "Zoom": "Zoomer", "Pan": "Déplacer", "Reset axes": "Réinitialiser les axes", "Reset view": "Réinitialiser la vue",
      "Autoscale": "Échelle automatique", "Zoom in": "Zoom avant", "Zoom out": "Zoom arrière",
      "Produced with Plotly.js": "Réalisé avec Plotly.js", "Double-click to zoom back out": "Double-cliquez pour dézoomer",
      "Snapshot succeeded": "Image enregistrée", "Taking snapshot - this may take a few seconds": "Capture en cours…",
      "Sorry, there was a problem downloading your snapshot!": "Le téléchargement de l'image a échoué."
    },
    format: {
      days: ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"],
      shortDays: ["dim.", "lun.", "mar.", "mer.", "jeu.", "ven.", "sam."],
      months: ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"],
      shortMonths: ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."],
      decimal: ",", thousands: " "
    }
  });
})();
