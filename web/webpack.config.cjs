const path = require('path');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');
const HtmlWebpackPlugin = require('html-webpack-plugin');

module.exports = {
  mode: 'production',
  devtool: 'source-map',
  target: 'web',
  entry: {
    main: [
      './js/app.mjs',
      './sass/app.scss',
    ],
    dark: [
      './sass/app-dark.scss',
    ],
  },
  output: {
    filename: 'static/js/[name].js',
    path: path.resolve(__dirname, '../'),
  },
  plugins: [
    new MiniCssExtractPlugin({
      filename: 'static/css/[name].css',
    }),
    new HtmlWebpackPlugin({
      filename: 'templates/index.template.html',
      template: './templates/index.template.html',
      inject: false,
    }),
    new HtmlWebpackPlugin({
      filename: 'templates/need_token.template.html',
      template: './templates/need_token.template.html',
      inject: false,
    }),
  ],
  module: {
    rules: [{
      test: /\.s[ac]ss$/i,
      use: [
        MiniCssExtractPlugin.loader,
        {
          loader: 'css-loader',
          options: {
            sourceMap: true,
          },
        },
        {
          loader: 'postcss-loader',
          options: {
            postcssOptions: {
              plugins: ['autoprefixer'],
            },
            sourceMap: true,
          },
        },
        {
          loader: 'sass-loader',
          options: {
            sourceMap: true,
          },
        },
      ],
    },
    {
      test: /\.m?js$/,
      exclude: /(node_modules|bower_components)/,
      resolve: {
        fullySpecified: false,
      },
      use: {
        loader: 'babel-loader',
        options: {
          presets: [
            [
              '@babel/preset-env',
              {
                corejs: '3.47',
                useBuiltIns: 'usage',
                bugfixes: true,
                targets: '>0.25%, not dead',
              },
            ],
          ],
          cacheDirectory: true,
        },
      },
    },
    ],
  },

  resolve: {
    extensions: ['.mjs', '.js'],
  },
};
