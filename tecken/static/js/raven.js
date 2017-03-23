$(function() {
  $(document).ready( function() {
    Raven.config($('body').attr('data-sentry-public-dsn')).install();
  });
});
