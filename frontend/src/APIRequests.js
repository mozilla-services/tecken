import React, { Component } from 'react'
import { Link } from 'react-router-dom'
import { observer } from 'mobx-react'

import store from './Store'

const DisplayAPIRequests = observer(
class DisplayAPIRequests extends Component {
  reset = event => {
    store.apiRequests = []
  }

  displayUrl = (url) => {
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
    // const request = this.props.request
    const requests = store.apiRequests
    if (!requests.length) {
      return null
    }
    // console.log('REQUESTS:', requests.length);
    return (
      <div style={{marginTop: 100}}>
        <hr/>
        <div className="notification">
          <button className="delete" onClick={this.reset} />
          <p><b>Tip!</b></p>
          <p>
            Every data request made, can be done outside the webapp. Just remember to pass an authentication header.
            {/* <br/>This time it was:
            <a href={fullUrl}><code>{fullUrl}</code></a> */}
          </p>
          {
            requests.map((request, i) => {
              const fullUrl = this.displayUrl(request.url)
              return <p key={i}>
                <code>curl -X {request.method} -H 'Auth-Token: <Link to="/tokens">YOURTOKENHERE</Link>' <a href={fullUrl}>{fullUrl}</a></code>
              </p>
            })
          }
        </div>
      </div>
    )

    // return null
    // if (!request || !request.url) return null
    // const fullUrl = this.displayUrl(request.url)
    // return (
    //   <div style={{marginTop: 100}}>
    //     <hr/>
    //     <div className="notification">
    //       <button className="delete" onClick={this.reset} />
    //       <p><b>Tip!</b></p>
    //       <p>
    //         Every data request made, can be done outside the webapp.
    //         <br/>This time it was:
    //         <a href={fullUrl}><code>{fullUrl}</code></a>
    //       </p>
    //       <p>
    //         Remember that you need to pass an authentication header. Full example:<br/>
    //         <code>curl -H 'Auth-Token: <Link to="/tokens">YOURTOKENHERE</Link>' {fullUrl}</code>
    //       </p>
    //     </div>
    //   </div>
    // )
  }
})


export default DisplayAPIRequests
