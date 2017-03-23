$(function() {
  // Ensure that all AJAX requests sent with jQuery have CSRF tokens
  var csrfToken = jQuery("input[name=csrfmiddlewaretoken]").val();
  $.ajaxSetup({
    beforeSend: function(xhr, settings) {
      // non-CSRF-safe method that isn't cross domain
      if (["GET", "HEAD", "OPTIONS", "TRACE"].indexOf(settings.Type) < 0 && !this.crossDomain) {
        xhr.setRequestHeader("X-CSRFToken", csrfToken);
      }
    }
  });
});
