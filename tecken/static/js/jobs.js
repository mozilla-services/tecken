$(function() {
  $.fn.atmoNotebook = function() {
    var container = this,
        content_given = container.attr('data-content-given'),
        download_url = container.attr('data-download-url');
    var fail = function() {
      container.html('<h4>Apologies, we could not load Notebook content.</h4>');
    };
    var current_script_path = function() {
      var scripts = $('script[src]');
      var current_script = scripts[scripts.length - 1].src;
      var current_script_chunks = current_script.split('/');
      var current_script_file = current_script_chunks[current_script_chunks.length - 1];
      return current_script.replace(current_script_file, '');
    };
    var render = function(data) {
      if (data) {
        var notebook = nb.parse(data);
        container.empty();
        container.append(notebook.render());
        Prism.plugins.autoloader.languages_path = current_script_path() + '../npm/prismjs/components/';
        Prism.highlightAll();
      };
    }
    if (content_given == 'true') {
      var content = container.children().filter('textarea').val();
      render(JSON.parse(content));
    } else if (jQuery.type(download_url) !== 'undefined') {
      $.get(download_url).done(render).fail(fail);
    }
  };
  AtmoCallbacks.add(function() {
    $('#notebook-content').atmoNotebook();
  });
});
