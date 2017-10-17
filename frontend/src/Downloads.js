import React from 'react'
import { Link } from 'react-router-dom'
import store from './Store'

class Downloads extends React.PureComponent {
  constructor(props) {
    super(props)
    this.state = {
      pageTitle: 'Downloads'
    }
  }

  componentDidMount() {
    document.title = this.state.pageTitle
    store.resetApiRequests()
  }

  render() {
    return (
      <div>
        <h1 className="title">{this.state.pageTitle}</h1>
        <p>
          <Link to="/downloads/missing">Downloads Missing</Link>
        </p>
        <p>
          <Link to="/downloads/microsoft">Microsoft Downloads</Link>
        </p>
      </div>
    )
  }
}

export default Downloads
