import React, { PureComponent } from 'react'
import store from './Store'

/* Global component that is used to display that any fetch() failed.
   Kinda equivalent of how jQuery.ajaxError works except we don't
   monkeypatch fetch(). XXX maybe we should.
*/
class FetchError extends PureComponent {
  resetFetchError = (event) => {
    store.fetchError = null
  }
  render() {
    const { error } = this.props
    // Allowing the only and first argument to be falsy is to make it
    // convenient to do things like `<FetchError errors={store.anyError}/>`
    // without having to wrap it in a conditional.
    if (!error) {
      return null
    }
    // error is a response object unless it's null
    return (
      <article className="message is-danger">
        <div className="message-header">
          <p>
            <strong>Server Response Error</strong>!
          </p>
          <button className="delete" onClick={this.resetFetchError}></button>
        </div>
        <div className="message-body">
          <p>
            Status: <code>{error.status}</code>
          </p>
          <p>
            URL: <code>{error.url}</code>
          </p>
        </div>
      </article>
    )
  }

}

export default FetchError
