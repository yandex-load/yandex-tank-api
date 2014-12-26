(function() {
  var app;

  app = angular.module("ng-tank-manager", ['ui.ace']);

  app.controller("TankManager", function($scope, $element) {
    var updateStatus;
    return updateStatus = function() {
      return $scope.status;
    };
  });

}).call(this);
