import React from 'react'
import FontAwesome from 'react-fontawesome'
import 'font-awesome/css/font-awesome.css'

export const Loading = () =>
  <p className="has-text-centered">
    <span className="icon is-large">
      <FontAwesome name="cog" spin size="5x" />
      <span className="sr-only">Loading...</span>
    </span>
  </p>
