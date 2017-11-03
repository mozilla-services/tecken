import React from 'react'
import { Link } from 'react-router-dom'
import { observer } from 'mobx-react'

import store from './Store'

const DisplayAPIRequests = observer(
  class DisplayAPIRequests extends React.Component {
    reset = event => {
      store.apiRequests = []
      window.sessionStorage.setItem('hide-api-requests', true)
    }

    displayUrl = url => {
      if (url.charAt(0) === '/') {
        // make local URLs absolute
        url = `${document.location.protocol}//${document.location.host}${url}`
      }
      // When doing local development, the hostname is most likely
      // 'localhost:3000' which gets proxied by the React dev server to
      // 'localhost:8000', let's make that easier.
      url = url.replace('localhost:3000/', 'localhost:8000/')
      return url
    }

    render() {
      if (window.sessionStorage.getItem('hide-api-requests')) {
        return null
      }
      const requests = store.apiRequests
      if (!requests.length) {
        return null
      }
      return (
        <div style={{ marginTop: 100 }}>
          <hr />
          <div className="notification">
            <button className="delete" onClick={this.reset} />
            <p>
              <b>Tip!</b>
            </p>
            <p>
              Every data request made, can be done outside the webapp. Just
              remember to pass an authentication header.
            </p>
            {requests.map((request, i) => {
              const fullUrl = this.displayUrl(request.url)
              return (
                <p key={i}>
                  {request.requiresAuth ? (
                    <code>
                      curl -X {request.method} -H 'Auth-Token:{' '}
                      <Link to="/tokens">YOURTOKENHERE</Link>'{' '}
                      <a href={fullUrl}>{fullUrl}</a>
                    </code>
                  ) : (
                    <code>
                      curl -X {request.method} <a href={fullUrl}>{fullUrl}</a>
                    </code>
                  )}
                </p>
              )
            })}
          </div>
        </div>
      )
    }
  }
)

export default DisplayAPIRequests
