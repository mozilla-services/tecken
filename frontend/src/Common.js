import React from 'react'
import FontAwesome from 'react-fontawesome'
import 'font-awesome/css/font-awesome.css'

export const Loading = () => (
  <p className="has-text-centered">
    <span className="icon is-large">
      <FontAwesome name="cog" spin size='5x'/>
      <span className="sr-only">Loading...</span>
    </span>
  </p>
)


export const FetchError = (response) => (
  // error is a response object
  <article className="message is-danger">
    <div className="message-header">
      <p><strong>Server Response Error</strong>!</p>
    </div>
    <div className="message-body">
      <p>Status: <code>{response.error.status}</code></p>
      <p>URL: <code>{response.error.url}</code></p>
    </div>
  </article>
)
