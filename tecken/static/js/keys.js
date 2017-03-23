$(function() {
  $.fn.atmoKeys = function(options) {
    var key_textarea = this,
        file_input = $(options.file_input),
        title_input = $(options.title_input);

    var readFile = function(file) {
      // Only process .pub files
      if (!file.name.match('.pub')) {
        alert('Dropped file name must end in ".pub".');
        event.stopPropagation();
        return;
      }
      var reader = new FileReader();
      // Closure to capture the file information.
      reader.onload = function(event) {
        // use the filename..
        var title = file.name.replace(/.pub/g, '');
        // or -- if available -- the user found in the key content
        if (event.target.result.length > 0) {
          var split_result = event.target.result.split(' ');
          if (split_result.length > 2) {
            title = split_result[split_result.length - 1];
          }
        }
        title_input.val(title).trigger('input');
        key_textarea.val(event.target.result).trigger('input');
      };

      // Read in the ssh key file as a data URL.
      reader.readAsText(file);
    }

    var handleFileSelect = function() {
      var input = $(this);
      $.each(input.get(0).files, function(index, file) {
        readFile(file);
      })
    }

    var handleFileDrop = function(event) {
      event.stopPropagation();
      event.preventDefault();

      var files = event.originalEvent.dataTransfer.files; // FileList object.

      $.each(files, function(index, file) {
        readFile(file);
      });
    }

    var handleDragOver = function(event) {
      event.stopPropagation();
      event.preventDefault();
      // Explicitly show this is a copy.
      event.originalEvent.dataTransfer.dropEffect = 'copy';
    }

    // Check for the various File API support.
    if (window.File && window.FileReader && window.FileList && window.Blob) {
      // Setup the dnd listeners.
      key_textarea.on('dragover', handleDragOver);
      key_textarea.on('drop', handleFileDrop);
      file_input.on('change', handleFileSelect);
    }
  };

  AtmoCallbacks.add(function() {
    $('#id_sshkey-key').atmoKeys({
        file_input: '#id_sshkey-key_file',
        title_input: '#id_sshkey-title',
    });
  });
});
