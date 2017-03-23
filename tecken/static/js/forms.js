$(function() {
  $.fn.atmoDatetimePicker = function() {
    // apply datetimepicker initialization
    $(this).datetimepicker({
      autoclose: true,
      startView: 'day',
      maxView: 'year',
      todayHighlight: true,
      todayBtn: true,
      format: 'yyyy-mm-dd hh:ii:ss'
    });
  };

  $.fn.atmoFormSubmission = function() {
    // Disable form submit buttons on form submission
    $(this).on('submit', function(event) {
      var $form = $(this);
      var $submit = $form.find('button[type=submit]');
      var $cancel = $form.find("a:contains('Cancel')");
      var $reset = $form.find('button[type=reset]');
      var submit_label = $submit.text();
      var wait_label = 'Please wait…';

      // disable submit button and change label
      $submit.addClass('disabled').find('.submit-button').text(wait_label);

      // hide cancel button
      $cancel.addClass('hidden');

      var reset_callback = function(event) {
        // re-enable submit button
        $submit.removeClass('disabled')
          .find('.submit-button')
          .text(submit_label);
        // show cancel button again
        $cancel.removeClass('hidden');
        // hide reset button
        $reset.addClass('hidden');
      };
      // show reset button to be able to reset form
      $reset.removeClass('hidden').click(reset_callback);
    });
  };

  $.fn.atmoFormValidation = function() {
    if ($(this).length) {
      $(this).parsley({
        trigger: 'focusin focusout change input',
        triggerAfterFailure: 'focusin focusout change input',
        animate: false,
        validationThreshold: 1,
        successClass: 'has-success',
        errorClass: 'has-error',
        classHandler: function(el) {
          return el.$element.closest('.form-group');
        },
        errorsContainer: function(el) {
          return el.$element.closest('.form-group');
        },
        errorsWrapper: '<span class="help-block">',
        errorTemplate: '<div></div>'
      });
    }
  }

  AtmoCallbacks.add(function() {
    $('.datetimepicker').atmoDatetimePicker();
    $('form').atmoFormValidation();
    $('form').atmoFormSubmission();
  });

});
